"""Free data collection tools for stock analysis using only open source and free APIs."""

import logging
import os

_logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import yfinance as yf

from . import _http

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment,misc]
try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

from crewai.tools import BaseTool
from pydantic import Field as _PydanticField

from ..models.stock_data import (
    CompanyInfo,
    EconomicData,
)
from ..models.stock_data import FundamentalData as FundamentalDataModel
from ..models.stock_data import (
    MarketData,
    NewsData,
)
from .cache import cached_tool

_VALID_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
_PERIOD_ALIASES = {
    "1-year": "1y",
    "1 year": "1y",
    "1yr": "1y",
    "12mo": "1y",
    "12m": "1y",
    "annual": "1y",
    "2-year": "2y",
    "2 years": "2y",
    "2yr": "2y",
    "5-year": "5y",
    "5 years": "5y",
    "5yr": "5y",
    "10-year": "10y",
    "10 years": "10y",
    "6-month": "6mo",
    "6 months": "6mo",
    "6m": "6mo",
    "half-year": "6mo",
    "3-month": "3mo",
    "3 months": "3mo",
    "3m": "3mo",
    "quarter": "3mo",
    "1-month": "1mo",
    "1 month": "1mo",
    "1m": "1mo",
    "month": "1mo",
    "1-day": "1d",
    "1 day": "1d",
    "day": "1d",
    "5-day": "5d",
    "5 days": "5d",
    "week": "5d",
}


def _normalize_period(period: str, default: str = "1y") -> str:
    """Coerce LLM-invented period strings ('1-year', '12 months') to valid
    yfinance periods; fall back to a sane default rather than erroring."""
    v = str(period or "").strip().lower()
    if v in _VALID_PERIODS:
        return v
    if v in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[v]
    compact = v.replace("-", "").replace(" ", "")
    for alias, norm in _PERIOD_ALIASES.items():
        if compact == alias.replace("-", "").replace(" ", ""):
            return norm
    _logger.warning("Invalid period %r — defaulting to %r", period, default)
    return default


def _detect_asset_type(symbol: str) -> str:
    """Return 'etf' or 'stock' based on yfinance quoteType."""
    try:
        qt = yf.Ticker(symbol).info.get("quoteType", "").upper()
        return "etf" if qt == "ETF" else "stock"
    except Exception:
        return "stock"


def resolve_symbol(symbol: str) -> Optional[Dict[str, str]]:
    """Cheap pre-flight check: does ``symbol`` resolve to a real security, and
    if so what's its display name? Used to fail fast and to surface the
    company/fund name before the full analysis flow starts.

    yfinance doesn't raise for a bogus ticker — ``.info`` just comes back
    near-empty (e.g. ``{'trailingPegRatio': None}``) — so validity is judged
    by whether a name is present, not by catching an exception.
    """
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return None
    name = info.get("shortName") or info.get("longName")
    if not name:
        return None
    asset_type = "etf" if (info.get("quoteType", "") or "").upper() == "ETF" else "stock"
    return {"name": name, "asset_type": asset_type}


def _fetch_top_holdings(ticker: "yf.Ticker") -> list:
    """Return list of top-10 holdings dicts or [] on failure."""
    try:
        df = ticker.funds_data.top_holdings
        return df.head(10).reset_index().to_dict("records")
    except Exception:
        return []


def _etf_fraction(*values: Any, pct_threshold: float) -> Optional[float]:
    """First non-None value, normalized to a fraction (0.0085 = 0.85%).

    yfinance is wildly inconsistent: ``ytdReturn`` / ``netExpenseRatio`` come as
    percent figures (85.32, 0.5), while ``annualReportExpenseRatio`` / ``yield``
    come as fractions (0.0085, 0.012). A value whose magnitude exceeds the
    per-field threshold is treated as already-percent and divided by 100, so
    everything downstream can consistently multiply by 100 for display.
    """
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:  # NaN
            continue
        return f / 100 if abs(f) > pct_threshold else f
    return None


def _compute_technical_summary(hist: "pd.DataFrame") -> Dict[str, Any]:
    """Pre-compute key technical indicators from raw OHLCV history.

    Returns a compact dict (~300 tokens) that gives the technical analyst
    everything it needs without raw row arrays (~4,500 tokens).
    """
    if hist is None or hist.empty:
        return {}

    close = hist["Close"]
    volume = hist["Volume"]
    high = hist["High"]
    low = hist["Low"]

    def _safe(val):
        try:
            v = float(val)
            return None if (v != v) else round(v, 4)  # NaN check
        except Exception:
            return None

    # SMAs
    sma_20 = _safe(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    sma_50 = _safe(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma_90 = _safe(close.rolling(90).mean().iloc[-1]) if len(close) >= 90 else None

    # RSI(14) — Wilder's smoothing (EWM with alpha=1/14) matches charting platforms
    rsi = None
    if len(close) >= 15:
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi_series = 100 - (100 / (1 + rs))
        rsi = _safe(rsi_series.iloc[-1])

    # MACD (12/26/9)
    macd_val = macd_signal = macd_hist = None
    if len(close) >= 26:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_val = _safe(macd_line.iloc[-1])
        macd_signal = _safe(signal_line.iloc[-1])
        macd_hist = _safe((macd_line - signal_line).iloc[-1])

    # Bollinger Bands (20, 2σ)
    bb_upper = bb_lower = None
    if len(close) >= 20:
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = _safe((sma20 + 2 * std20).iloc[-1])
        bb_lower = _safe((sma20 - 2 * std20).iloc[-1])

    # ATR(14)
    atr = None
    if len(close) >= 15:
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = _safe(tr.rolling(14).mean().iloc[-1])

    # Volume stats — guard against NaN values from illiquid/newly-listed tickers
    vol_avg_raw = float(volume.mean()) if len(volume) > 0 else 0.0
    vol_avg = 0.0 if vol_avg_raw != vol_avg_raw else vol_avg_raw
    vol_latest_raw = float(volume.iloc[-1]) if len(volume) > 0 else 0.0
    vol_latest = 0.0 if vol_latest_raw != vol_latest_raw else vol_latest_raw
    vol_vs_avg_pct = round(vol_latest / vol_avg * 100, 1) if vol_avg > 0 else None

    # Price context
    current = _safe(close.iloc[-1])
    prev = _safe(close.iloc[-2]) if len(close) >= 2 else None
    period_high = _safe(close.max())
    period_low = _safe(close.min())

    return {
        "current_price": current,
        "prev_close": prev,
        "period_high_90d": period_high,
        "period_low_90d": period_low,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "sma_90": sma_90,
        "rsi_14": rsi,
        "macd": macd_val,
        "macd_signal": macd_signal,
        "macd_histogram": macd_hist,
        "bb_upper_20": bb_upper,
        "bb_lower_20": bb_lower,
        "atr_14": atr,
        "volume_latest": int(vol_latest),
        "volume_avg_90d": int(vol_avg),
        "volume_vs_avg_pct": vol_vs_avg_pct,
    }


class YahooFinanceTool(BaseTool):
    """Tool for collecting data from Yahoo Finance (FREE)."""

    name: str = "Yahoo Finance Data Collector"
    description: str = (
        "Collects comprehensive stock data from Yahoo Finance including prices, fundamentals, and company information"
    )

    def _run(self, symbol: str, period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
        """Collect data from Yahoo Finance. period accepts 1d/5d/1mo/3mo/6mo/1y/2y/5y/10y/ytd/max."""
        # Normalize BEFORE the cache key is computed (@cached_tool hashes the
        # args/kwargs it receives), so LLM-invented variants like "1-year"
        # share a cache entry with the canonical "1y" instead of fragmenting it.
        return self._run_normalized(
            symbol=symbol, period=_normalize_period(period), interval=interval
        )

    @cached_tool()
    def _run_normalized(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)

            # Get basic info
            info = ticker.info

            # Get historical data
            hist = ticker.history(period=period, interval=interval)

            # Get company info
            company_info = CompanyInfo(
                symbol=symbol,
                name=info.get("longName", symbol),
                sector=info.get("sector"),
                industry=info.get("industry"),
                country=info.get("country"),
                exchange=info.get("exchange"),
                currency=info.get("currency"),
                website=info.get("website"),
                description=info.get("longBusinessSummary"),
                employees=info.get("fullTimeEmployees"),
                founded_year=info.get("founded"),
                ceo=(
                    info.get("companyOfficers", [{}])[0].get("name")
                    if info.get("companyOfficers")
                    else None
                ),
                headquarters=(
                    info.get("city") + ", " + info.get("state")
                    if info.get("city") and info.get("state")
                    else None
                ),
            )

            # Get market data
            current_price = hist["Close"].iloc[-1] if not hist.empty else 0
            previous_close = info.get("previousClose", current_price)
            day_change = current_price - previous_close
            day_change_percent = (day_change / previous_close * 100) if previous_close != 0 else 0

            market_data = MarketData(
                symbol=symbol,
                current_price=current_price,
                previous_close=previous_close,
                day_change=day_change,
                day_change_percent=day_change_percent,
                volume=hist["Volume"].iloc[-1] if not hist.empty else 0,
                avg_volume=info.get("averageVolume"),
                market_cap=info.get("marketCap"),
                high_52w=info.get("fiftyTwoWeekHigh"),
                low_52w=info.get("fiftyTwoWeekLow"),
                beta=info.get("beta"),
                timestamp=datetime.now(),
            )

            # Get fundamental data
            fundamental_data = FundamentalDataModel(
                pe_ratio=info.get("trailingPE"),
                pb_ratio=info.get("priceToBook"),
                ps_ratio=info.get("priceToSalesTrailing12Months"),
                peg_ratio=info.get("pegRatio"),
                ev_ebitda=info.get("enterpriseToEbitda"),
                roe=info.get("returnOnEquity"),
                roa=info.get("returnOnAssets"),
                gross_margin=info.get("grossMargins"),
                operating_margin=info.get("operatingMargins"),
                net_margin=info.get("profitMargins"),
                debt_to_equity=info.get("debtToEquity"),
                current_ratio=info.get("currentRatio"),
                quick_ratio=info.get("quickRatio"),
                market_cap=info.get("marketCap"),
                enterprise_value=info.get("enterpriseValue"),
                total_revenue=info.get("totalRevenue"),
                net_income=info.get("netIncomeToCommon"),
                total_assets=info.get("totalAssets"),
                total_liabilities=info.get("totalLiab"),
                total_equity=info.get("totalStockholderEquity"),
                free_cash_flow=info.get("freeCashflow"),
                dividend_yield=info.get("dividendYield"),
                dividend_per_share=info.get("dividendRate"),
                payout_ratio=info.get("payoutRatio"),
                timestamp=datetime.now(),
            )

            asset_type = "etf" if info.get("quoteType", "").upper() == "ETF" else "stock"

            # Short interest — institutional positioning signal, free from the
            # same info payload (no extra API call)
            short_interest = {}
            if info.get("sharesShort"):
                spf = info.get("shortPercentOfFloat")
                prior = info.get("sharesShortPriorMonth")
                current_short = info.get("sharesShort")
                short_interest = {
                    "short_ratio_days_to_cover": info.get("shortRatio"),
                    "short_pct_of_float": round(spf * 100, 2) if spf else None,
                    "shares_short": current_short,
                    "shares_short_prior_month": prior,
                    "mom_change_pct": (
                        round((current_short - prior) / prior * 100, 1)
                        if current_short and prior
                        else None
                    ),
                }

            result: Dict[str, Any] = {
                "asset_type": asset_type,
                "company_info": company_info.dict(),
                "market_data": market_data.dict(),
                "technical_summary": _compute_technical_summary(hist),
                "short_interest": short_interest,
                "fundamental_data": fundamental_data.dict(),
            }

            if asset_type == "etf":
                result["etf_profile"] = {
                    "fund_family": info.get("fundFamily"),
                    "category": info.get("category"),
                    "total_assets_bn": (
                        round(info.get("totalAssets", 0) / 1e9, 2)
                        if info.get("totalAssets")
                        else None
                    ),
                    # Expense ratio: prefer fraction fields, fall back to
                    # netExpenseRatio (a percent figure, e.g. 0.5 = 0.50%).
                    "expense_ratio": _etf_fraction(
                        info.get("annualReportExpenseRatio"),
                        info.get("totalExpenseRatio"),
                        info.get("netExpenseRatio"),
                        pct_threshold=0.1,
                    ),
                    "distribution_yield": _etf_fraction(
                        info.get("yield"),
                        info.get("trailingAnnualDividendYield"),
                        pct_threshold=1.0,
                    ),
                    # ytdReturn arrives as a percent figure (85.32 = 85.32%).
                    "ytd_return": _etf_fraction(info.get("ytdReturn"), pct_threshold=1.5),
                    "three_year_return": _etf_fraction(
                        info.get("threeYearAverageReturn"), pct_threshold=1.5
                    ),
                    "five_year_return": _etf_fraction(
                        info.get("fiveYearAverageReturn"), pct_threshold=1.5
                    ),
                    "turnover_ratio": _etf_fraction(
                        info.get("annualHoldingsTurnover"), pct_threshold=1.0
                    ),
                    "inception_date": info.get("fundInceptionDate"),
                    "index_tracked": info.get("underlyingSymbol") or info.get("category"),
                    "top_holdings": _fetch_top_holdings(ticker),
                }

            # ── Quarterly income statement (revenue + margins history) ──────────
            try:
                qis = ticker.quarterly_income_stmt
                if qis is not None and not qis.empty:
                    qtrs = {}
                    for col in list(qis.columns)[:5]:  # last 5 quarters
                        row: Dict[str, Any] = {}
                        for metric in [
                            "Total Revenue",
                            "Gross Profit",
                            "Operating Income",
                            "Net Income",
                            "EBITDA",
                        ]:
                            if metric in qis.index:
                                v = qis.loc[metric, col]
                                row[metric.lower().replace(" ", "_")] = (
                                    None
                                    if (v is None or (isinstance(v, float) and v != v))
                                    else int(v)
                                )
                        label = col.date().isoformat() if hasattr(col, "date") else str(col)[:10]
                        qtrs[label] = row
                    result["quarterly_income"] = qtrs
            except Exception as _exc:
                _logger.debug("quarterly_income_stmt failed: %s", _exc)

            # ── Earnings beat/miss track record ───────────────────────────────
            try:
                ed = ticker.get_earnings_dates(limit=8)
                if ed is not None and not ed.empty:
                    earnings_hist = []
                    for idx, row in ed.iterrows():
                        eps_est = row.get("EPS Estimate")
                        eps_act = row.get("Reported EPS")
                        surprise = row.get("Surprise(%)")
                        date_str = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
                        # Only include rows where we have at least one real value
                        if eps_est is not None or eps_act is not None:
                            earnings_hist.append(
                                {
                                    "date": date_str,
                                    "eps_estimate": (
                                        None
                                        if (
                                            eps_est is None
                                            or (isinstance(eps_est, float) and eps_est != eps_est)
                                        )
                                        else round(float(eps_est), 4)
                                    ),
                                    "eps_actual": (
                                        None
                                        if (
                                            eps_act is None
                                            or (isinstance(eps_act, float) and eps_act != eps_act)
                                        )
                                        else round(float(eps_act), 4)
                                    ),
                                    "surprise_pct": (
                                        None
                                        if (
                                            surprise is None
                                            or (
                                                isinstance(surprise, float) and surprise != surprise
                                            )
                                        )
                                        else round(float(surprise), 2)
                                    ),
                                }
                            )
                    if earnings_hist:
                        result["earnings_history"] = earnings_hist
            except Exception as _exc:
                _logger.debug("earnings_dates failed: %s", _exc)

            # ── Recent news headlines ──────────────────────────────────────────
            try:
                raw_news = ticker.news or []
                news_items = []
                for n in raw_news[:12]:
                    if not isinstance(n, dict):
                        continue
                    # yfinance wraps newer news in a "content" sub-dict
                    content = n.get("content", n)
                    if isinstance(content, dict):
                        title = content.get("title", "")
                        provider = content.get("provider", {})
                        publisher = (
                            provider.get("displayName", "") if isinstance(provider, dict) else ""
                        )
                        pub_date = content.get("pubDate", "")
                        summary = (content.get("summary") or content.get("description") or "")[:200]
                    else:
                        title = n.get("title", "")
                        publisher = n.get("publisher", "")
                        pub_date = str(n.get("providerPublishTime", ""))
                        summary = ""
                    if title:
                        news_items.append(
                            {
                                "title": title,
                                "publisher": publisher,
                                "published": str(pub_date)[:20],
                                "summary": summary,
                            }
                        )
                if news_items:
                    result["recent_news"] = news_items
            except Exception as _exc:
                _logger.debug("ticker.news failed: %s", _exc)

            return result

        except Exception as e:
            return {"error": f"Failed to collect Yahoo Finance data: {str(e)}"}


def _sec_extract_section(plain_text: str, markers: List[str], max_chars: int = 4000) -> str:
    """Locate a named section in plain text from an SEC filing and return up to max_chars.

    Searches for every occurrence of the marker strings (case-insensitive) and picks
    the first one that has substantial body content (>= 500 chars before the next
    section header).  This skips table-of-contents entries, which are short stubs.
    """
    text_upper = plain_text.upper()

    # Collect ALL occurrence positions for all markers
    positions: List[int] = []
    for marker in markers:
        m_upper = marker.upper()
        start = 0
        while True:
            idx = text_upper.find(m_upper, start)
            if idx < 0:
                break
            positions.append(idx)
            start = idx + 1

    positions.sort()

    for pos in positions:
        # Read a large window to measure how much content exists before the next section
        window = plain_text[pos : pos + max_chars + 2000]
        # Trim at the next "ITEM N" / "ITEM NA" pattern after the first 400 chars
        # (400 char buffer ensures we don't clip the header line itself)
        next_item = re.search(r"\bITEM\s+\d+[A-Z]?\b", window[400:], re.IGNORECASE)
        body = window[: 400 + next_item.start()] if next_item else window[:max_chars]
        stripped = body.strip()
        # Skip TOC stubs and boilerplate forward-looking-statement disclaimers.
        # Real section bodies (MD&A, Risk Factors) have at least 2000 substantive chars.
        if len(stripped) < 2000:
            continue
        return stripped[:max_chars]

    return ""


def _sec_unwrap_ixbrl(href: str) -> str:
    """Strip the EDGAR iXBRL viewer prefix from a document href.

    EDGAR wraps inline XBRL documents in /ix?doc=/Archives/... viewer URLs.
    We need the bare /Archives/... path to fetch the actual HTML content.
    """
    # e.g. /ix?doc=/Archives/edgar/data/.../tsla-20260331.htm
    #   or https://www.sec.gov/ix?doc=/Archives/...
    m = re.search(r'[?&]doc=(/Archives/[^\s&"]+)', href)
    if m:
        return "https://www.sec.gov" + m.group(1)
    return href


def _sec_find_primary_doc_url(index_html: str, index_url: str, form_type: str) -> Optional[str]:
    """Parse an EDGAR filing index page and return the URL of the primary filing document.

    EDGAR index pages have a table with columns: Seq | Description | Document | Type | Size.
    We find the row whose Type cell matches form_type.  iXBRL viewer wrappers are stripped.
    """
    if BeautifulSoup is None:
        return None
    soup = BeautifulSoup(index_html, "html.parser")

    # Primary method: look for the tableFile table and match the Type column
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            type_text = cells[3].get_text(strip=True).strip().upper()
            if type_text == form_type.upper():
                # Document href is in cells[2]
                a_tag = cells[2].find("a")
                if a_tag and a_tag.get("href"):
                    raw = a_tag["href"]
                    full = urljoin("https://www.sec.gov", raw)
                    return _sec_unwrap_ixbrl(full)

    # Fallback: find any .htm link that looks like the main filing (not an exhibit)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_lower = href.lower()
        if not (href_lower.endswith(".htm") or ".htm" in href_lower):
            continue
        # Exclude obvious exhibits and auxiliary files
        if any(x in href_lower for x in ["ex", "exhibit", "xsd", "cal", "def", "lab", "pre"]):
            continue
        full = urljoin("https://www.sec.gov", href)
        return _sec_unwrap_ixbrl(full)

    return None


class FreeSECFilingTool(BaseTool):
    """Tool for collecting SEC filing data using free EDGAR access."""

    name: str = "Free SEC Filing Data Collector"
    description: str = (
        "Collects SEC filing data using free EDGAR access. "
        "Returns the MD&A section (management discussion and analysis), "
        "risk factors, and filing metadata."
    )

    @cached_tool(ttl=86400)
    def _run(self, symbol: str, form_type: str = "10-K", limit: int = 1) -> Dict[str, Any]:
        """Collect SEC filing data: MD&A, Risk Factors, and key metadata."""
        from ..config.settings import settings as _edgar_settings

        edgar_email = _edgar_settings.sec_edgar_email
        if edgar_email == "contact@example.com":
            _logger.warning(
                "SEC_EDGAR_EMAIL is not configured — set it in .env to avoid EDGAR throttling"
            )
        headers = {
            "User-Agent": f"Stock Analysis Tool ({edgar_email})",
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov",
        }

        try:
            # ── Step 1: get list of filings via EDGAR Atom feed ───────────────
            search_url = "https://www.sec.gov/cgi-bin/browse-edgar"
            params = {
                "action": "getcompany",
                "CIK": symbol,
                "type": form_type,
                "dateb": "",
                "owner": "exclude",
                "start": "0",
                "count": str(limit),
                "output": "atom",
            }
            response = _http.get(search_url, params=params, headers=headers, timeout=20)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            filings: List[Dict[str, Any]] = []
            for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                f: Dict[str, Any] = {}
                t = entry.find(".//{http://www.w3.org/2005/Atom}title")
                if t is not None:
                    f["title"] = t.text
                lk = entry.find(".//{http://www.w3.org/2005/Atom}link")
                if lk is not None:
                    f["link"] = lk.get("href")
                u = entry.find(".//{http://www.w3.org/2005/Atom}updated")
                if u is not None:
                    f["updated"] = u.text
                filings.append(f)

            if not filings:
                return {"error": f"No {form_type} filings found for {symbol}"}

            index_url = filings[0].get("link", "")
            mdna_text = ""
            risk_text = ""
            doc_url = ""

            if index_url:
                # ── Step 2: fetch the filing index page ───────────────────────
                idx_resp = _http.get(index_url, headers=headers, timeout=20)
                idx_resp.raise_for_status()

                # ── Step 3: find the URL of the primary filing document ────────
                doc_url = _sec_find_primary_doc_url(idx_resp.text, index_url, form_type) or ""

                if doc_url:
                    # ── Step 4: fetch the actual 10-K / 10-Q document ──────────
                    # Stream response and read up to 600 KB to limit memory usage.
                    # Context-managed so the connection is released back to the
                    # pool even when the loop below breaks out early.
                    raw_html = b""
                    with _http.get(doc_url, headers=headers, timeout=30, stream=True) as doc_resp:
                        doc_resp.raise_for_status()
                        for chunk in doc_resp.iter_content(chunk_size=32_768):
                            raw_html += chunk
                            if len(raw_html) >= 600_000:
                                break

                    # Convert HTML → plain text once
                    if BeautifulSoup is not None:
                        plain = BeautifulSoup(raw_html, "html.parser").get_text(separator="\n")
                    else:
                        plain = raw_html.decode("utf-8", errors="ignore")

                    # ── Step 5: extract MD&A section ──────────────────────────
                    # 10-K: Item 7  |  10-Q: Item 2
                    mdna_markers = [
                        "MANAGEMENT'S DISCUSSION AND ANALYSIS",
                        "MANAGEMENT S DISCUSSION AND ANALYSIS",
                        "ITEM 7.",
                        "ITEM 7 ",
                        "ITEM 2.",
                        "ITEM 2 ",
                    ]
                    mdna_text = _sec_extract_section(plain, mdna_markers, max_chars=5000)

                    # ── Step 6: extract Risk Factors section ──────────────────
                    risk_markers = [
                        "RISK FACTORS",
                        "ITEM 1A.",
                        "ITEM 1A ",
                    ]
                    risk_text = _sec_extract_section(plain, risk_markers, max_chars=3500)

            return {
                "filings": filings,
                "form_type": form_type,
                "doc_url": doc_url,
                "mdna": mdna_text,
                "risk_factors": risk_text,
                "sections_found": {
                    "mdna": bool(mdna_text),
                    "risk_factors": bool(risk_text),
                },
            }

        except Exception as exc:
            return {"error": f"Failed to collect SEC filing data: {exc}"}


class FreeFREDTool(BaseTool):
    """Tool for collecting economic data from FRED (FREE)."""

    name: str = "Free FRED Economic Data Collector"
    description: str = (
        "Collects economic indicators from Federal Reserve Economic Data (FRED) - FREE"
    )
    api_key: str = _PydanticField(default="demo", exclude=True)

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        resolved = api_key or os.getenv("FRED_API_KEY") or "demo"
        super().__init__(api_key=resolved, **kwargs)

    @cached_tool(ttl=86400)  # FRED macro data is stable; cache for 24 h
    def _run(
        self, series_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Collect economic data from FRED."""
        try:
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            if end_date is None:
                end_date = datetime.now().strftime("%Y-%m-%d")

            # FRED API URL
            base_url = "https://api.stlouisfed.org/fred"

            # Get series data
            data_url = f"{base_url}/series/observations"
            data_params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": start_date,
                "observation_end": end_date,
            }

            response = _http.get(data_url, params=data_params, timeout=20)
            response.raise_for_status()

            data = response.json()

            # Get series info
            info_url = f"{base_url}/series"
            info_params = {"series_id": series_id, "api_key": self.api_key, "file_type": "json"}

            info_response = _http.get(info_url, params=info_params, timeout=20)
            info_response.raise_for_status()

            series_info = info_response.json()

            return {"data": data, "info": series_info, "series_id": series_id}

        except requests.exceptions.RequestException as exc:
            # Never surface str(exc) here — the FRED request URL (including
            # api_key=<real_key>) is embedded in HTTPError/RequestException
            # messages and this dict flows straight into the calling agent's
            # LLM context.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            return {
                "error": (
                    f"Failed to collect FRED data for {series_id} " f"(HTTP {status})"
                    if status
                    else f"Failed to collect FRED data for {series_id}"
                )
            }
        except Exception:
            return {"error": f"Failed to collect FRED data for {series_id}"}


class FreeNewsTool(BaseTool):
    """Tool for collecting news data using free sources."""

    name: str = "Free News Data Collector"
    description: str = (
        "Collects news articles and sentiment data using free RSS feeds (Google News and others) and web scraping"
    )

    @cached_tool(ttl=1800)
    def _run(self, symbol: str, query: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Collect news data for a stock using free sources."""
        from urllib.parse import quote as _url_quote

        try:
            symbol = symbol.strip().upper()
            if not symbol or " " in symbol or len(symbol) > 15:
                return {
                    "error": f"'{symbol}' is not a valid ticker symbol",
                    "news_data": [],
                    "total_count": 0,
                }

            encoded_symbol = _url_quote(symbol)

            if not query:
                query = f"{symbol} stock news"

            news_data = []
            # Tracks whether at least one source attempt completed without
            # raising, so a total outage (every source's try/except caught an
            # exception) can be flagged with a top-level "error" and skip the
            # cache (see @cached_tool, which never caches error dicts) — a
            # genuine "no news found" result (some source succeeded, just
            # empty) is still cached normally.
            any_source_ok = False

            # ── Primary: Google News RSS (keyless, rich coverage, scoped by the
            # query so no symbol-mention filter is needed) ─────────────────────
            if feedparser is not None:
                try:
                    gn_url = (
                        "https://news.google.com/rss/search?q="
                        + _url_quote(f"{symbol} stock")
                        + "&hl=en-US&gl=US&ceid=US:en"
                    )
                    gn_resp = _http.get(gn_url, timeout=15)
                    gn_resp.raise_for_status()
                    feed = feedparser.parse(gn_resp.content)
                    for entry in feed.entries[:limit]:
                        published_at = datetime.now()
                        if getattr(entry, "published_parsed", None):
                            published_at = datetime(*entry.published_parsed[:6])
                        news_data.append(
                            NewsData(
                                title=entry.get("title", ""),
                                summary=entry.get("summary", "")[:300],
                                url=entry.get("link", ""),
                                source=(entry.get("source") or {}).get("title", "Google News"),
                                published_at=published_at,
                                sentiment_score=None,
                                relevance_score=0.9,
                                tags=[],
                            )
                        )
                    any_source_ok = True
                except Exception as e:
                    _logger.debug("Google News RSS failed: %s", e)

            # ── Fallback chain: query-scoped feeds tried in order until one
            # yields items (no symbol-mention filter needed for these) ─────────
            fallback_feeds = [
                (
                    "Bing News",
                    "https://www.bing.com/news/search?q="
                    + _url_quote(f"{symbol} stock")
                    + "&format=rss",
                ),
                (
                    "Yahoo Finance",
                    f"https://feeds.finance.yahoo.com/rss/2.0/headline"
                    f"?s={encoded_symbol}&region=US&lang=en-US",
                ),
            ]
            for source_name, feed_url in fallback_feeds if feedparser is not None else []:
                if news_data:
                    break
                try:
                    fb_resp = _http.get(feed_url, timeout=15)
                    fb_resp.raise_for_status()
                    feed = feedparser.parse(fb_resp.content)
                    for entry in feed.entries[:limit]:
                        published_at = datetime.now()
                        if getattr(entry, "published_parsed", None):
                            published_at = datetime(*entry.published_parsed[:6])
                        news_data.append(
                            NewsData(
                                title=entry.get("title", ""),
                                summary=entry.get("summary", "")[:300],
                                url=entry.get("link", ""),
                                source=source_name,
                                published_at=published_at,
                                sentiment_score=None,
                                relevance_score=0.85,
                                tags=[],
                            )
                        )
                    any_source_ok = True
                except Exception as e:
                    _logger.debug("%s RSS failed: %s", source_name, e)

            # Tertiary: broad market feeds (symbol-mention filtered)
            rss_feeds = [
                "https://feeds.marketwatch.com/marketwatch/marketpulse/",
                "https://feeds.bloomberg.com/markets/news.rss",
            ]

            for feed_url in rss_feeds if feedparser is not None else []:
                try:
                    tert_resp = _http.get(feed_url, timeout=15)
                    tert_resp.raise_for_status()
                    feed = feedparser.parse(tert_resp.content)
                    for entry in feed.entries[: limit // len(rss_feeds)]:
                        # Check if the symbol is mentioned in the title or summary
                        title = entry.get("title", "")
                        summary = entry.get("summary", "")

                        if (
                            symbol.lower() in title.lower()
                            or symbol.lower() in summary.lower()
                            or symbol.lower() in entry.get("description", "").lower()
                        ):

                            # Extract published date
                            published_at = datetime.now()
                            if hasattr(entry, "published_parsed") and entry.published_parsed:
                                published_at = datetime(*entry.published_parsed[:6])

                            news_data.append(
                                NewsData(
                                    title=title,
                                    summary=summary,
                                    url=entry.get("link", ""),
                                    source=feed.feed.get("title", "Unknown"),
                                    published_at=published_at,
                                    sentiment_score=None,
                                    relevance_score=0.8,
                                    tags=[],
                                )
                            )
                    any_source_ok = True
                except Exception as e:
                    _logger.debug("RSS feed %s failed: %s", feed_url, e)
                    continue

            # Web scraping from financial news sites (only Yahoo Finance is
            # actually parsed below — MarketWatch/SeekingAlpha were fetched
            # but discarded, wasting requests against sites that can block us)
            news_sites = [
                f"https://finance.yahoo.com/quote/{encoded_symbol}/news",
            ]

            for site_url in news_sites if BeautifulSoup is not None else []:
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }

                    response = _http.get(site_url, headers=headers, timeout=15)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.content, "html.parser")

                    # Look for news articles (this is site-specific)
                    if "yahoo.com" in site_url:
                        articles = soup.find_all("h3", class_="Mb(5px)")
                        for article in articles[:5]:
                            link = article.find("a")
                            if link:
                                title = link.get_text(strip=True)
                                href = link.get("href", "")
                                if href and not href.startswith("http"):
                                    href = urljoin(site_url, href)

                                news_data.append(
                                    NewsData(
                                        title=title,
                                        summary="",
                                        url=href,
                                        source="Yahoo Finance",
                                        published_at=datetime.now(),
                                        sentiment_score=None,
                                        relevance_score=0.9,
                                        tags=[],
                                    )
                                )
                    any_source_ok = True

                except Exception as e:
                    _logger.debug("Web scraping %s failed: %s", site_url, e)
                    continue

            # Remove duplicates based on URL
            seen_urls = set()
            unique_news = []
            for news in news_data:
                if news.url not in seen_urls:
                    seen_urls.add(news.url)
                    unique_news.append(news)

            result: Dict[str, Any] = {
                "news_data": [n.dict() for n in unique_news[:limit]],
                "total_count": len(unique_news),
            }
            if not any_source_ok and not unique_news:
                # Every source's attempt raised — this is a total outage, not a
                # genuine "no news" result, so it must not be cached (see
                # @cached_tool, which skips caching dicts containing "error").
                result["error"] = "all news sources failed"
            return result

        except Exception as e:
            return {"error": f"Failed to collect news data: {str(e)}"}


def _market_macro_snapshot() -> Dict[str, Any]:
    """Market-traded macro proxies via yfinance — works even when FRED is
    rate-limited or down. Returns latest value and 1-month change per proxy."""
    proxies = [
        ("^VIX", "vix_volatility_index"),
        ("^TNX", "treasury_10y_yield_pct"),
        ("^GSPC", "sp500_index"),
        ("CL=F", "wti_crude_usd"),
        ("DX-Y.NYB", "dollar_index"),
    ]
    out: Dict[str, Any] = {}
    for ticker_sym, label in proxies:
        try:
            hist = yf.Ticker(ticker_sym).history(period="1mo")
            if hist is None or hist.empty:
                continue
            latest = float(hist["Close"].iloc[-1])
            first = float(hist["Close"].iloc[0])
            out[label] = {
                "latest": round(latest, 2),
                "change_1m_pct": round((latest - first) / first * 100, 1) if first else None,
            }
        except Exception as exc:
            _logger.debug("macro proxy %s failed: %s", ticker_sym, exc)
    return out


class FreeEconomicDataTool(BaseTool):
    """Tool for collecting economic data from free sources."""

    name: str = "Free Economic Data Collector"
    description: str = (
        "Collects economic data from FRED (GDP, CPI, Fed funds, unemployment, "
        "sentiment, payrolls) plus market-traded macro proxies (VIX, 10Y Treasury "
        "yield, S&P 500, WTI crude, dollar index) that work even when FRED is "
        "rate-limited. Free, no paid key required."
    )
    fred_api_key: str = _PydanticField(default="demo", exclude=True)

    def __init__(self, fred_api_key: Optional[str] = None, **kwargs):
        if fred_api_key is None:
            from ..config.settings import settings as _settings

            fred_api_key = _settings.fred_api_key or os.getenv("FRED_API_KEY") or "demo"
        super().__init__(fred_api_key=fred_api_key, **kwargs)

    @cached_tool(ttl=86400)
    def _run(self, country: str = "US", indicators: Optional[str] = None) -> Dict[str, Any]:
        """Collect economic data. indicators is an optional JSON array of FRED series IDs e.g. '["GDPC1","UNRATE"]'."""
        try:
            if indicators is None or not str(indicators).strip():
                indicator_list = [
                    "GDPC1",  # Real GDP
                    "CPIAUCSL",  # Consumer Price Index
                    "FEDFUNDS",  # Federal Funds Rate
                    "UNRATE",  # Unemployment Rate
                    "UMCSENT",  # Consumer Sentiment
                    "PAYEMS",  # Nonfarm Payrolls
                ]
            elif isinstance(indicators, list):
                indicator_list = indicators
            else:
                import json as _json

                indicator_list = _json.loads(str(indicators).strip())
            indicators = indicator_list

            economic_data = {}

            # Helper to fetch observations + info in parallel per indicator
            def _fetch_single_indicator(indicator):
                try:
                    base_url = "https://api.stlouisfed.org/fred"

                    # Get series data
                    data_url = f"{base_url}/series/observations"
                    data_params = {
                        "series_id": indicator,
                        "api_key": self.fred_api_key,
                        "file_type": "json",
                        "observation_start": (datetime.now() - timedelta(days=365 * 2)).strftime(
                            "%Y-%m-%d"
                        ),
                        "observation_end": datetime.now().strftime("%Y-%m-%d"),
                    }

                    response = _http.get(data_url, params=data_params, timeout=20)
                    response.raise_for_status()
                    data = response.json()

                    # Get series info
                    info_url = f"{base_url}/series"
                    info_params = {
                        "series_id": indicator,
                        "api_key": self.fred_api_key,
                        "file_type": "json",
                    }

                    info_response = _http.get(info_url, params=info_params, timeout=20)
                    info_response.raise_for_status()
                    series_info = info_response.json()

                    return indicator, {"data": data, "info": series_info}
                except requests.exceptions.RequestException as exc:
                    # Never log str(exc) — it embeds the request URL with the
                    # real api_key in the query string.
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    _logger.debug("Failed to get FRED series %s (HTTP %s)", indicator, status)
                    return indicator, None
                except Exception:
                    _logger.debug("Failed to get FRED series %s", indicator)
                    return indicator, None

            # Concurrently fetch all FRED series
            with ThreadPoolExecutor(max_workers=min(len(indicators), 6)) as executor:
                futures = {executor.submit(_fetch_single_indicator, ind): ind for ind in indicators}
                for future in as_completed(futures):
                    ind = futures[future]
                    try:
                        res = future.result()
                        if res and res[1] is not None:
                            economic_data[res[0]] = res[1]
                    except Exception as e:
                        _logger.debug("Future failed for FRED series %s: %s", ind, e)

            # Create EconomicData model
            gdp_data = economic_data.get("GDPC1", {}).get("data", {}).get("observations", [])
            cpi_data = economic_data.get("CPIAUCSL", {}).get("data", {}).get("observations", [])
            fed_funds_data = (
                economic_data.get("FEDFUNDS", {}).get("data", {}).get("observations", [])
            )
            unemployment_data = (
                economic_data.get("UNRATE", {}).get("data", {}).get("observations", [])
            )

            # Calculate growth rates
            gdp_growth = None
            if gdp_data and len(gdp_data) >= 2:
                gdp_values = [
                    float(obs.get("value", 0)) for obs in gdp_data if obs.get("value") != "."
                ]
                if len(gdp_values) >= 2:
                    gdp_growth = (gdp_values[-1] - gdp_values[-2]) / gdp_values[-2] * 100

            inflation_rate = None
            if cpi_data and len(cpi_data) >= 12:
                cpi_values = [
                    float(obs.get("value", 0)) for obs in cpi_data if obs.get("value") != "."
                ]
                if len(cpi_values) >= 12:
                    inflation_rate = (cpi_values[-1] - cpi_values[-12]) / cpi_values[-12] * 100

            interest_rate = None
            if fed_funds_data:
                fed_values = [
                    float(obs.get("value", 0)) for obs in fed_funds_data if obs.get("value") != "."
                ]
                if fed_values:
                    interest_rate = fed_values[-1]

            unemployment_rate = None
            if unemployment_data:
                unemp_values = [
                    float(obs.get("value", 0))
                    for obs in unemployment_data
                    if obs.get("value") != "."
                ]
                if unemp_values:
                    unemployment_rate = unemp_values[-1]

            economic_data_model = EconomicData(
                gdp_growth=gdp_growth,
                inflation_rate=inflation_rate,
                interest_rate=interest_rate,
                unemployment_rate=unemployment_rate,
                consumer_confidence=None,
                business_confidence=None,
                currency_strength=None,
                country=country,
                timestamp=datetime.now(),
            )

            # Build a compact per-indicator summary — richer context, no raw arrays
            def _indicator_summary(obs_list, name):
                vals = [
                    float(o["value"]) for o in obs_list if o.get("value") not in (".", None, "")
                ]
                if not vals:
                    return {"latest": None, "trend": "unknown"}
                latest = vals[-1]
                qoq = (
                    round((latest - vals[-4]) / abs(vals[-4]) * 100, 2) if len(vals) >= 4 else None
                )
                yoy = (
                    round((latest - vals[-12]) / abs(vals[-12]) * 100, 2)
                    if len(vals) >= 12
                    else None
                )
                if qoq is None:
                    trend = "unknown"
                elif qoq > 0.2:
                    trend = "rising"
                elif qoq < -0.2:
                    trend = "falling"
                else:
                    trend = "stable"
                return {
                    "latest": round(latest, 4),
                    "qoq_change_pct": qoq,
                    "yoy_change_pct": yoy,
                    "trend": trend,
                }

            indicator_summaries = {
                "GDPC1_real_gdp": _indicator_summary(gdp_data, "GDPC1"),
                "CPIAUCSL_inflation": _indicator_summary(cpi_data, "CPIAUCSL"),
                "FEDFUNDS_rate": _indicator_summary(fed_funds_data, "FEDFUNDS"),
                "UNRATE_unemployment": _indicator_summary(unemployment_data, "UNRATE"),
                "UMCSENT_sentiment": _indicator_summary(
                    economic_data.get("UMCSENT", {}).get("data", {}).get("observations", []),
                    "UMCSENT",
                ),
                "PAYEMS_payrolls": _indicator_summary(
                    economic_data.get("PAYEMS", {}).get("data", {}).get("observations", []),
                    "PAYEMS",
                ),
            }

            market_indicators = _market_macro_snapshot()
            result = {
                "economic_data": economic_data_model.dict(),
                "indicator_summaries": indicator_summaries,
                # Market-traded proxies double as a fallback when FRED is
                # rate-limited (demo key) or unreachable
                "market_indicators": market_indicators,
            }
            if not economic_data and not market_indicators:
                return {"error": "No economic data available from FRED or market proxies"}
            if not economic_data:
                # All FRED series failed but market proxies are available.
                # Add a note so agents know FRED trends are unavailable, and
                # cache with the normal TTL since proxy data is still fresh.
                result["note"] = "FRED series unavailable; indicator_summaries reflect no data"
            return result

        except Exception as e:
            # FRED path crashed — market proxies may still serve macro context
            fallback = _market_macro_snapshot()
            if fallback:
                return {
                    "economic_data": {},
                    "indicator_summaries": {},
                    "market_indicators": fallback,
                    "note": "FRED data unavailable; market-traded proxies provided instead",
                }
            return {"error": f"Failed to collect economic data: {str(e)}"}


class FreeWebSearchTool(BaseTool):
    """Tool for web search using free methods."""

    name: str = "Free Web Search Tool"
    description: str = "Performs web searches using free methods like DuckDuckGo and web scraping"

    @cached_tool(ttl=3600)
    def _run(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """Perform web search using free methods."""
        if BeautifulSoup is None:
            return {"error": "bs4 is not installed; install it with: pip install beautifulsoup4"}
        try:
            # Use DuckDuckGo search (free)
            search_url = "https://html.duckduckgo.com/html/"
            params = {"q": query, "kl": "us-en"}

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            response = _http.get(search_url, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            results = []
            search_results = soup.find_all("div", class_="result")

            for result in search_results[:num_results]:
                title_elem = result.find("a", class_="result__a")
                snippet_elem = result.find("a", class_="result__snippet")
                url_elem = result.find("a", class_="result__url")

                if title_elem:
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get("href", "")
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                    results.append({"title": title, "url": url, "snippet": snippet})

            return {"results": results, "query": query, "total_results": len(results)}

        except Exception as e:
            return {"error": f"Failed to perform web search: {str(e)}"}


class FreeCompetitorAnalysisTool(BaseTool):
    """Tool for competitor analysis using free data sources."""

    name: str = "Free Competitor Analysis Tool"
    description: str = (
        "Analyzes competitors using free data sources like Yahoo Finance and web scraping"
    )

    @cached_tool(ttl=43200)
    def _run(self, symbol: str, industry: Optional[str] = None) -> Dict[str, Any]:
        """Analyze competitors using free sources."""
        try:
            # Get company info first
            yahoo_tool = YahooFinanceTool()
            company_data = yahoo_tool._run(symbol=symbol)

            if "error" in company_data:
                return company_data

            company_info = company_data.get("company_info", {})
            sector = company_info.get("sector")
            industry = industry or company_info.get("industry")

            # Find competitors using web search
            search_tool = FreeWebSearchTool()
            search_query = f"{symbol} competitors {industry} {sector}"
            search_results = search_tool._run(search_query, num_results=10)

            # Common stop words/non-ticker capitalized words
            exclude_words = {
                "AND",
                "OR",
                "BUT",
                "FOR",
                "THE",
                "A",
                "AN",
                "IN",
                "ON",
                "AT",
                "BY",
                "TO",
                "OF",
                "US",
                "UK",
                "EU",
                "USA",
                "SEC",
                "CEO",
                "CFO",
                "ETF",
                "PE",
                "EPS",
                "GDP",
                "CPI",
                "NYSE",
                "NASDAQ",
                "AMEX",
                "OTC",
                "FTSE",
                "DAX",
                "CAC",
                "ASX",
                "TSX",
                "S&P",
                "SPY",
                "INDEX",
                "STOCK",
                "SHARE",
                "BOND",
                "DEBT",
                "CASH",
                "ASSET",
                "FUND",
                "TRUST",
                "JAN",
                "FEB",
                "MAR",
                "APR",
                "MAY",
                "JUN",
                "JUL",
                "AUG",
                "SEP",
                "OCT",
                "NOV",
                "DEC",
                "FY",
                "Q1",
                "Q2",
                "Q3",
                "Q4",
                "TTM",
                "YTD",
                "CAGR",
                "IPO",
                "M&A",
                "R&D",
                "FCF",
                "REIT",
                "NAV",
                "AUM",
                "ESG",
                "P/E",
                "P/B",
                "P/S",
                "PEG",
                "EV",
                "EBIT",
                "EBITDA",
                "COMP",
                "INC",
                "CORP",
                "LTD",
                "LLC",
                "PLC",
                "CO",
                "SA",
                "AG",
                "NV",
                "BV",
                "GMBH",
                "NEW",
                "YORK",
                "CITY",
                "STREET",
                "WALL",
                "BANK",
                "MARKET",
                "GROWTH",
                "VAL",
                "DIV",
                "NEWS",
                "INFO",
                "DATA",
                "WEB",
                "SITE",
                "URL",
                "HTML",
                "JSON",
                "XML",
                "PDF",
                "API",
            }

            # Collect candidate symbols
            candidates_raw = []
            for result in search_results.get("results", []):
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                text = f"{title} {snippet}"
                potential_symbols = re.findall(r"\b[A-Z]{1,5}\b", text)
                for c in potential_symbols:
                    c_upper = c.upper()
                    if (
                        c_upper != symbol.upper()
                        and len(c_upper) >= 2
                        and len(c_upper) <= 5
                        and c_upper not in exclude_words
                    ):
                        candidates_raw.append(c_upper)

            # Deduplicate and limit candidates to check (max 8) to avoid yfinance spam
            candidates = list(dict.fromkeys(candidates_raw))[:8]

            # Helper to validate a competitor symbol with ONE cheap info call —
            # candidates come from scraped web text and are mostly junk, so a
            # full data collection per candidate would waste 5-6 API calls each
            def _validate_competitor(candidate):
                try:
                    info = yf.Ticker(candidate).info or {}
                    if not info.get("marketCap"):
                        return None
                    return {
                        "symbol": candidate,
                        "name": info.get("shortName") or info.get("longName") or candidate,
                        "sector": info.get("sector"),
                        "industry": info.get("industry"),
                        "market_cap": info.get("marketCap"),
                        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                    }
                except Exception:
                    pass
                return None

            # Concurrently validate competitor candidates
            competitors_list = []
            with ThreadPoolExecutor(max_workers=min(len(candidates), 4)) as executor:
                futures = {executor.submit(_validate_competitor, c): c for c in candidates}
                for future in as_completed(futures):
                    res = future.result()
                    if res:
                        competitors_list.append(res)

            # Sort/deduplicate list
            seen_symbols = set()
            unique_competitors = []
            for comp in competitors_list:
                if comp["symbol"] not in seen_symbols:
                    seen_symbols.add(comp["symbol"])
                    unique_competitors.append(comp)

            return {
                "competitors": unique_competitors[:10],  # Limit to top 10
                "industry": industry,
                "sector": sector,
                "total_found": len(unique_competitors),
            }

        except Exception as e:
            return {"error": f"Failed to analyze competitors: {str(e)}"}


class FreeIndustryAnalysisTool(BaseTool):
    """Tool for industry analysis using free data sources."""

    name: str = "Free Industry Analysis Tool"
    description: str = "Analyzes industry trends using free data sources"

    @cached_tool(ttl=43200)
    def _run(self, industry: str, sector: Optional[str] = None) -> Dict[str, Any]:
        """Analyze industry using free sources."""
        try:
            # Instantiate tools
            search_tool = FreeWebSearchTool()
            economic_tool = FreeEconomicDataTool()
            news_tool = FreeNewsTool()

            search_query = f"{industry} sector analysis trends {datetime.now().year}"

            # Fetch sub-sources concurrently
            results = {}
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_search = executor.submit(search_tool._run, search_query, num_results=10)
                future_economic = executor.submit(economic_tool._run)
                future_news = executor.submit(
                    news_tool._run, industry, query=f"{industry} industry news"
                )

                try:
                    results["search"] = future_search.result(timeout=30)
                except Exception as e:
                    results["search"] = {"error": str(e)}

                try:
                    results["economic"] = future_economic.result(timeout=30)
                except Exception as e:
                    results["economic"] = {"error": str(e)}

                try:
                    results["news"] = future_news.result(timeout=30)
                except Exception as e:
                    results["news"] = {"error": str(e)}

            result: Dict[str, Any] = {
                "industry": industry,
                "sector": sector,
                "search_results": results["search"].get("results", []),
                "economic_context": results["economic"].get("economic_data", {}),
                "news_sentiment": results["news"].get("news_data", []),
                "analysis_timestamp": datetime.now().isoformat(),
            }
            # Only flag a top-level error when literally every sub-source
            # failed — a partial result (e.g. news down but search/economic
            # ok) is still a legitimate, cacheable result.
            if all(
                isinstance(results.get(name), dict) and "error" in results[name]
                for name in ("search", "economic", "news")
            ):
                result["error"] = "all industry analysis sub-sources failed"
            return result

        except Exception as e:
            return {"error": f"Failed to analyze industry: {str(e)}"}


class ParallelDataCollectionTool(BaseTool):
    """Fetches data from all enabled sources concurrently and merges the results."""

    name: str = "Parallel Data Collection Tool"
    description: str = (
        "Concurrently fetches Yahoo Finance prices, SEC filings, FRED economic data, "
        "and news for a stock symbol, returning a merged result dict."
    )

    def _run(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        from ..config.settings import settings
        from .company_intel import (
            AnalystDataTool,
            FinancialStatementsTool,
            OwnershipTool,
        )
        from .social_sentiment import SocialSentimentTool

        tasks = [
            ("yahoo_finance", YahooFinanceTool()._run, {"symbol": symbol, "period": period}),
            ("analyst_data", AnalystDataTool()._run, {"symbol": symbol}),
            ("financial_statements", FinancialStatementsTool()._run, {"symbol": symbol}),
            ("ownership", OwnershipTool()._run, {"symbol": symbol}),
            ("social_sentiment", SocialSentimentTool()._run, {"symbol": symbol}),
        ]

        if settings.sec_edgar_enabled:
            tasks.append(("sec_filings", FreeSECFilingTool()._run, {"symbol": symbol}))
        if settings.fred_enabled:
            tasks.append(
                ("economic_data", FreeEconomicDataTool(fred_api_key=settings.fred_api_key)._run, {})
            )
        if settings.rss_feeds_enabled:
            tasks.append(("news", FreeNewsTool()._run, {"symbol": symbol}))

        results: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as executor:
            futures = {executor.submit(fn, **kwargs): name for name, fn, kwargs in tasks}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=30)
                except Exception as exc:
                    results[name] = {"error": str(exc)}

        results["symbol"] = symbol
        results["collection_timestamp"] = datetime.now().isoformat()
        return results
