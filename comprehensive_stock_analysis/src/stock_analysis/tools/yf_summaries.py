"""Compact summarizers over a yfinance Ticker.

Each function takes an already-constructed ``yf.Ticker`` and returns a small,
JSON-serializable dict (top-N lists, latest values, deltas — never raw frames)
sized to fit comfortably in an LLM prompt. Every accessor is guarded: a missing
or failing yfinance property yields a partial dict, never an exception.

Sharing one Ticker across all summarizers minimizes Yahoo Finance API calls.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from . import _http

_logger = logging.getLogger(__name__)

# Common capitalized tokens that regex-match the ticker pattern but aren't
# tickers; filtered out of web-search results in fetch_peer_symbols().
_TICKER_STOPWORDS = {
    "AND",
    "OR",
    "BUT",
    "FOR",
    "THE",
    "WITH",
    "FROM",
    "INTO",
    "OVER",
    "ITS",
    "INC",
    "CORP",
    "LLC",
    "LTD",
    "PLC",
    "CO",
    "USA",
    "US",
    "UK",
    "EU",
    "NYSE",
    "NASDAQ",
    "AMEX",
    "OTC",
    "ETF",
    "CEO",
    "CFO",
    "IPO",
    "ESG",
    "SEC",
    "GDP",
    "CPI",
    "TTM",
    "YTD",
    "EPS",
    "PE",
    "FY",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "NEW",
    "TOP",
    "VS",
    "ALSO",
    "MORE",
    "WHAT",
    "WHO",
    "HOW",
    "WHY",
    "ARE",
    "IS",
    "IT",
    "AI",
    "API",
    "FAQ",
    "HTML",
}


def _num(v: Any, digits: int = 4) -> Optional[float]:
    """Coerce to a rounded float; NaN/None/garbage → None."""
    try:
        f = float(v)
        return None if f != f else round(f, digits)
    except Exception:
        return None


def _millions(v: Any) -> Optional[float]:
    f = _num(v, 6)
    return None if f is None else round(f / 1e6, 1)


def _row(df: pd.DataFrame, labels: List[str]) -> Optional[pd.Series]:
    """Tolerant row lookup — yfinance row labels vary across versions."""
    for label in labels:
        if label in df.index:
            return df.loc[label]
    return None


# yfinance returns 13F *filer* entities, so one asset manager arrives split
# across several rows ("Vanguard Capital Management", "Vanguard Portfolio
# Management"). Reported raw that understates concentration, and because the
# list is then truncated the split entries also push genuine holders off it.
# Matched on a lowercased substring of the filer name; first match wins.
_HOLDER_FAMILIES: List[Tuple[str, str]] = [
    ("vanguard", "Vanguard Group"),
    ("blackrock", "BlackRock"),
    ("state street", "State Street Global Advisors"),
    ("geode", "Geode Capital Management"),
    ("fmr ", "FMR (Fidelity)"),
    ("fidelity", "FMR (Fidelity)"),
    ("t. rowe", "T. Rowe Price"),
    ("capital research", "Capital Group"),
    ("capital world", "Capital Group"),
    ("morgan stanley", "Morgan Stanley"),
    ("jpmorgan", "JPMorgan"),
    ("j.p. morgan", "JPMorgan"),
    ("goldman sachs", "Goldman Sachs"),
    ("northern trust", "Northern Trust"),
    ("invesco", "Invesco"),
    ("wellington", "Wellington Management"),
]


def _holder_family(name: str) -> str:
    """Map a 13F filer name onto its economic owner, or return it unchanged."""
    low = name.lower()
    for needle, family in _HOLDER_FAMILIES:
        if needle in low:
            return family
    return name


def _aggregate_holders(
    records: List[Dict[str, Any]], top: int = 8
) -> List[Dict[str, Any]]:
    """Combine filer rows into economic holders, then take the largest ``top``.

    Aggregation happens before truncation — doing it after would keep the split
    rows competing for the same slots.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    for r in records:
        raw = str(r.get("Holder", "")).strip()
        if not raw:
            continue
        family = _holder_family(raw)
        entry = merged.setdefault(
            family,
            {"holder": family, "pct_held": None, "value_usd_m": None, "filers": 0},
        )
        entry["filers"] += 1
        if (v := _num(r.get("pctHeld"))) is not None:
            entry["pct_held"] = round((entry["pct_held"] or 0.0) + v * 100, 2)
        if (m := _millions(r.get("Value"))) is not None:
            entry["value_usd_m"] = round((entry["value_usd_m"] or 0.0) + m, 2)
    rows = sorted(
        merged.values(),
        key=lambda e: e["pct_held"] or e["value_usd_m"] or 0,
        reverse=True,
    )
    for e in rows:
        # Only meaningful where a merge actually happened; drop the noise.
        if e["filers"] < 2:
            e.pop("filers")
    return rows[:top]


def _date_label(col: Any) -> str:
    try:
        return col.date().isoformat()
    except Exception:
        return str(col)[:10]


# US equity regular session, in exchange local time. Used only to decide
# whether today's daily bar has settled.
_MARKET_TZ = "America/New_York"
_MARKET_CLOSE_HOUR = 16


def last_settled_close(ticker: Any) -> Dict[str, Any]:
    """The most recent *completed* daily close, with the session it belongs to.

    yfinance's last daily bar is today's bar while the session is running, so
    its close is a live quote that keeps moving. Reporting it as a close is
    simply untrue mid-session — a note generated at 11:27 said IBM "closed at
    $237.45 on August 19" while the market was open and the price was $236.53
    an hour later.

    Returns ``{price, date, basis}`` where ``basis`` names what the figure is,
    so callers can label it honestly rather than guessing.
    """
    out: Dict[str, Any] = {}
    try:
        hist = ticker.history(period="10d", interval="1d")
        if hist is None or hist.empty:
            return out
        from datetime import time as _time
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo(_MARKET_TZ))
        session_over = now.time() >= _time(_MARKET_CLOSE_HOUR, 0)

        rows = [(idx, float(r["Close"])) for idx, r in hist.iterrows()]
        # Drop today's bar unless the session has actually finished. On a
        # weekend or holiday the newest bar is already an earlier day, so this
        # is a no-op and needs no separate calendar.
        if rows and rows[-1][0].date() == now.date() and not session_over:
            rows = rows[:-1]
        if not rows:
            return out
        idx, close = rows[-1]
        out = {
            "price": round(close, 2),
            "date": _date_label(idx),
            "basis": "last close",
        }
    except Exception as exc:
        _logger.debug("last settled close failed: %s", exc)
    return out


# ── Analyst consensus, estimates, and rating changes ──────────────────────────


def summarize_analyst_data(ticker: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    try:
        pt = ticker.analyst_price_targets or {}
        current = _num(pt.get("current"))
        mean = _num(pt.get("mean"))
        out["price_targets"] = {
            "current_price": current,
            "low": _num(pt.get("low")),
            "mean": mean,
            "median": _num(pt.get("median")),
            "high": _num(pt.get("high")),
            "implied_upside_pct": (
                round((mean - current) / current * 100, 1) if mean and current else None
            ),
        }
    except Exception as exc:
        _logger.debug("analyst_price_targets failed: %s", exc)

    try:
        rec = ticker.recommendations
        if rec is not None and not rec.empty:
            out["recommendation_trend"] = [
                {
                    "period": str(r.get("period")),
                    "strong_buy": int(r.get("strongBuy") or 0),
                    "buy": int(r.get("buy") or 0),
                    "hold": int(r.get("hold") or 0),
                    "sell": int(r.get("sell") or 0),
                    "strong_sell": int(r.get("strongSell") or 0),
                }
                for r in rec.head(3).to_dict("records")
            ]
    except Exception as exc:
        _logger.debug("recommendations failed: %s", exc)

    try:
        ud = ticker.upgrades_downgrades
        if ud is not None and not ud.empty:
            cutoff = datetime.now() - timedelta(days=180)
            recent = (
                ud[ud.index >= pd.Timestamp(cutoff)] if hasattr(ud.index, "tz") else ud
            )
            out["recent_rating_changes"] = [
                {
                    "date": _date_label(idx),
                    "firm": str(row.get("Firm", "")),
                    "action": str(row.get("Action", "")),
                    "to_grade": str(row.get("ToGrade", "")),
                    "from_grade": str(row.get("FromGrade", "")),
                    "price_target": _num(row.get("currentPriceTarget")),
                }
                for idx, row in recent.head(8).iterrows()
            ]
    except Exception as exc:
        _logger.debug("upgrades_downgrades failed: %s", exc)

    def _estimate_block(df: Any, value_keys: List[str]) -> Dict[str, Any]:
        block: Dict[str, Any] = {}
        if df is None or df.empty:
            return block
        for period, row in df.iterrows():
            entry = {
                k: _num(row.get(src))
                for k, src in zip(
                    ("avg", "low", "high", "year_ago", "analysts", "growth_pct"),
                    value_keys,
                )
                if src in row.index
            }
            if "growth" in row.index and entry.get("growth_pct") is not None:
                entry["growth_pct"] = round(entry["growth_pct"] * 100, 1)
            block[str(period)] = entry
        return block

    try:
        out["eps_estimates"] = _estimate_block(
            ticker.earnings_estimate,
            ["avg", "low", "high", "yearAgoEps", "numberOfAnalysts", "growth"],
        )
    except Exception as exc:
        _logger.debug("earnings_estimate failed: %s", exc)

    try:
        rev = ticker.revenue_estimate
        if rev is not None and not rev.empty:
            out["revenue_estimates_m"] = {}
            for period, row in rev.iterrows():
                out["revenue_estimates_m"][str(period)] = {
                    "avg": _millions(row.get("avg")),
                    "growth_pct": (
                        round(g * 100, 1)
                        if (g := _num(row.get("growth"))) is not None
                        else None
                    ),
                    "analysts": _num(row.get("numberOfAnalysts"), 0),
                }
    except Exception as exc:
        _logger.debug("revenue_estimate failed: %s", exc)

    try:
        revisions = ticker.eps_revisions
        if revisions is not None and not revisions.empty:
            out["eps_revisions"] = {
                str(period): {
                    "up_30d": _num(row.get("upLast30days"), 0),
                    "down_30d": _num(row.get("downLast30days"), 0),
                }
                for period, row in revisions.iterrows()
            }
    except Exception as exc:
        _logger.debug("eps_revisions failed: %s", exc)

    return out


# ── Insider and institutional ownership ───────────────────────────────────────


def summarize_ownership(ticker: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    try:
        mh = ticker.major_holders
        if mh is not None and not mh.empty:
            values = mh["Value"] if "Value" in mh.columns else mh.iloc[:, 0]
            breakdown = dict(zip(mh.index, values))
            out["holders_breakdown"] = {
                "insider_pct": (
                    round(v * 100, 2)
                    if (v := _num(breakdown.get("insidersPercentHeld"))) is not None
                    else None
                ),
                "institution_pct": (
                    round(v * 100, 2)
                    if (v := _num(breakdown.get("institutionsPercentHeld"))) is not None
                    else None
                ),
                "institution_count": _num(breakdown.get("institutionsCount"), 0),
            }
    except Exception as exc:
        _logger.debug("major_holders failed: %s", exc)

    try:
        ih = ticker.institutional_holders
        if ih is not None and not ih.empty:
            out["top_institutions"] = _aggregate_holders(ih.to_dict("records"))
    except Exception as exc:
        _logger.debug("institutional_holders failed: %s", exc)

    try:
        it = ticker.insider_transactions
        if it is not None and not it.empty:
            recent = it.head(10)
            txns = []
            buys = sells = 0
            for _, r in recent.iterrows():
                text = str(r.get("Text", "") or r.get("Transaction", "")).lower()
                kind = (
                    "sell"
                    if "sale" in text
                    else ("buy" if ("purchase" in text or "buy" in text) else "other")
                )
                if kind == "buy":
                    buys += 1
                elif kind == "sell":
                    sells += 1
                txns.append(
                    {
                        "date": _date_label(r.get("Start Date")),
                        "insider": str(r.get("Insider", "")),
                        "position": str(r.get("Position", "")),
                        "type": kind,
                        "shares": _num(r.get("Shares"), 0),
                        "value_usd_m": _millions(r.get("Value")),
                    }
                )
            out["insider_transactions"] = txns
            out["insider_recent_summary"] = {
                "buys": buys,
                "sells": sells,
                "sampled": len(txns),
            }
    except Exception as exc:
        _logger.debug("insider_transactions failed: %s", exc)

    return out


# ── Financial statements (annual, last 3 FY) ──────────────────────────────────


def summarize_financial_statements(ticker: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    try:
        inc = ticker.income_stmt
        if inc is not None and not inc.empty:
            cols = list(inc.columns)[:4]
            revenue = _row(inc, ["Total Revenue", "TotalRevenue", "Operating Revenue"])
            gross = _row(inc, ["Gross Profit", "GrossProfit"])
            op = _row(
                inc,
                [
                    "Operating Income",
                    "OperatingIncome",
                    "Total Operating Income As Reported",
                ],
            )
            net = _row(
                inc, ["Net Income", "Net Income Common Stockholders", "NetIncome"]
            )
            annual: Dict[str, Any] = {}
            for i, col in enumerate(cols[:3]):
                label = _date_label(col)
                rev_v = _millions(revenue.get(col)) if revenue is not None else None
                prev_v = (
                    _millions(revenue.get(cols[i + 1]))
                    if revenue is not None and i + 1 < len(cols)
                    else None
                )
                annual[label] = {
                    "revenue_m": rev_v,
                    "gross_profit_m": (
                        _millions(gross.get(col)) if gross is not None else None
                    ),
                    "operating_income_m": (
                        _millions(op.get(col)) if op is not None else None
                    ),
                    "net_income_m": (
                        _millions(net.get(col)) if net is not None else None
                    ),
                    "revenue_yoy_pct": (
                        round((rev_v - prev_v) / abs(prev_v) * 100, 1)
                        if rev_v is not None and prev_v
                        else None
                    ),
                }
            out["annual_income"] = annual
    except Exception as exc:
        _logger.debug("income_stmt failed: %s", exc)

    try:
        bs = ticker.balance_sheet
        if bs is not None and not bs.empty:
            cols = list(bs.columns)[:3]
            assets = _row(bs, ["Total Assets", "TotalAssets"])
            # These labels are NOT equivalent — the first includes short-term
            # investments, the others do not. Whichever one yfinance happens to
            # expose changes the concept, not just the vintage, which is how one
            # report quoted $76,651M and $76,843M for "cash" in adjacent
            # sections. Report the matched label so the concept is named.
            cash_labels = [
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Cash Equivalents",
                "Cash Financial",
            ]
            cash = _row(bs, cash_labels)
            cash_label = next((lb for lb in cash_labels if lb in bs.index), None)
            if cash_label:
                out["cash_basis"] = cash_label
            debt = _row(bs, ["Total Debt", "TotalDebt"])
            equity = _row(
                bs,
                [
                    "Stockholders Equity",
                    "Common Stock Equity",
                    "Total Equity Gross Minority Interest",
                ],
            )
            out["balance_sheet"] = {
                _date_label(col): {
                    "total_assets_m": (
                        _millions(assets.get(col)) if assets is not None else None
                    ),
                    "cash_and_sti_m": (
                        _millions(cash.get(col)) if cash is not None else None
                    ),
                    "total_debt_m": (
                        _millions(debt.get(col)) if debt is not None else None
                    ),
                    "stockholders_equity_m": (
                        _millions(equity.get(col)) if equity is not None else None
                    ),
                }
                for col in cols
            }
    except Exception as exc:
        _logger.debug("balance_sheet failed: %s", exc)

    try:
        cf = ticker.cashflow
        if cf is not None and not cf.empty:
            cols = list(cf.columns)[:3]
            ocf = _row(
                cf,
                [
                    "Operating Cash Flow",
                    "Cash Flow From Continuing Operating Activities",
                ],
            )
            capex = _row(cf, ["Capital Expenditure", "CapitalExpenditure"])
            fcf = _row(cf, ["Free Cash Flow", "FreeCashFlow"])
            buyback = _row(cf, ["Repurchase Of Capital Stock"])
            divs = _row(cf, ["Cash Dividends Paid", "Common Stock Dividend Paid"])
            out["cash_flow"] = {
                _date_label(col): {
                    "operating_cf_m": (
                        _millions(ocf.get(col)) if ocf is not None else None
                    ),
                    "capex_m": _millions(capex.get(col)) if capex is not None else None,
                    "free_cash_flow_m": (
                        _millions(fcf.get(col)) if fcf is not None else None
                    ),
                    "buybacks_m": (
                        _millions(buyback.get(col)) if buyback is not None else None
                    ),
                    "dividends_paid_m": (
                        _millions(divs.get(col)) if divs is not None else None
                    ),
                }
                for col in cols
            }
    except Exception as exc:
        _logger.debug("cashflow failed: %s", exc)

    return out


# ── Options-market sentiment ──────────────────────────────────────────────────


def summarize_options_sentiment(ticker: Any) -> Dict[str, Any]:
    try:
        expiries = ticker.options
        if not expiries:
            return {"available": False, "note": "no listed options"}
        # Prefer an expiry ~2–6 weeks out (front-week chains are noisy)
        target = datetime.now() + timedelta(days=14)
        expiry = next(
            (e for e in expiries if datetime.strptime(e, "%Y-%m-%d") >= target),
            expiries[-1],
        )
        chain = ticker.option_chain(expiry)
        calls, puts = chain.calls, chain.puts

        call_oi = float(calls["openInterest"].fillna(0).sum())
        put_oi = float(puts["openInterest"].fillna(0).sum())
        call_vol = float(calls["volume"].fillna(0).sum())
        put_vol = float(puts["volume"].fillna(0).sum())

        spot = None
        try:
            spot = _num((ticker.analyst_price_targets or {}).get("current"))
        except Exception:
            pass

        def _atm_iv(df: pd.DataFrame) -> Optional[float]:
            if spot is None or df.empty:
                return None
            nearest = df.iloc[(df["strike"] - spot).abs().argsort()[:3]]
            iv = _num(nearest["impliedVolatility"].mean())
            return round(iv * 100, 1) if iv is not None else None

        return {
            "available": True,
            "expiry": expiry,
            "put_call_oi_ratio": round(put_oi / call_oi, 2) if call_oi else None,
            "put_call_volume_ratio": round(put_vol / call_vol, 2) if call_vol else None,
            "total_call_oi": int(call_oi),
            "total_put_oi": int(put_oi),
            "atm_call_iv_pct": _atm_iv(calls),
            "atm_put_iv_pct": _atm_iv(puts),
        }
    except Exception as exc:
        _logger.debug("options summary failed: %s", exc)
        return {"available": False, "note": str(exc)[:120]}


# ── Dividends and splits ──────────────────────────────────────────────────────


def summarize_dividends_splits(ticker: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        d = ticker.dividends
        if d is not None and len(d) > 0:
            out["recent_dividends"] = [
                {"date": _date_label(idx), "amount": _num(val)}
                for idx, val in d.tail(8).items()
            ]
            # 5-year dividend CAGR from annual sums. The current calendar year
            # is dropped: it is still in progress, so its partial total would be
            # compared against full years and read as a dividend cut. MSFT with
            # two of four 2026 payments banked scored -4.6% while the payout was
            # actually rising $0.75 -> $0.91.
            annual = d.groupby(d.index.year).sum()
            annual = annual[annual.index < datetime.now().year]
            if len(annual) >= 6:
                first, last = float(annual.iloc[-6]), float(annual.iloc[-1])
                if first > 0:
                    out["dividend_cagr_5y_pct"] = round(
                        ((last / first) ** 0.2 - 1) * 100, 1
                    )
                    out["dividend_cagr_window"] = (
                        f"{int(annual.index[-6])}-{int(annual.index[-1])}"
                    )
    except Exception as exc:
        _logger.debug("dividends failed: %s", exc)
    try:
        s = ticker.splits
        if s is not None and len(s) > 0:
            out["last_split"] = {
                "date": _date_label(s.index[-1]),
                "ratio": _num(s.iloc[-1]),
            }
    except Exception as exc:
        _logger.debug("splits failed: %s", exc)
    return out


# ── ETF portfolio details ─────────────────────────────────────────────────────


def summarize_etf_portfolio(ticker: Any) -> Dict[str, Any]:
    """Sector weightings, asset classes, and top holdings for funds/ETFs."""
    out: Dict[str, Any] = {}
    try:
        fd = ticker.funds_data
    except Exception:
        return out
    try:
        sw = fd.sector_weightings
        if sw:
            out["sector_weightings_pct"] = {
                k: round(float(v) * 100, 2)
                for k, v in sw.items()
                if _num(v) is not None
            }
    except Exception as exc:
        _logger.debug("sector_weightings failed: %s", exc)
    try:
        ac = fd.asset_classes
        if ac:
            out["asset_classes_pct"] = {
                k: round(float(v) * 100, 2)
                for k, v in ac.items()
                if _num(v) is not None
            }
    except Exception as exc:
        _logger.debug("asset_classes failed: %s", exc)
    try:
        th = fd.top_holdings
        if th is not None and not th.empty:
            out["top_holdings"] = th.head(10).reset_index().to_dict("records")
    except Exception as exc:
        _logger.debug("top_holdings failed: %s", exc)
    return out


# ── Peer comparison ───────────────────────────────────────────────────────────


def fetch_peer_symbols(
    symbol: str,
    company_name: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    limit: int = 4,
) -> List[str]:
    """Discover real business competitors via a keyless web search.

    Yahoo's ``recommendationsbysymbol`` endpoint returns co-viewed/correlated
    tickers, not actual competitors — it once paired PEGA (enterprise workflow
    automation) with WEX (fleet-card payments) and Cognex (machine-vision
    hardware). Instead, search for the company's named competitors and
    extract ticker-shaped tokens from the results, then keep only candidates
    that validate against yfinance (and, when available, share the subject's
    sector) so unrelated companies don't slip through.
    """
    try:
        from bs4 import BeautifulSoup  # optional dependency, imported lazily
    except ImportError:
        _logger.debug("bs4 not installed; cannot discover peers via web search")
        return []

    query = f"{company_name or symbol} main competitors publicly traded stock ticker"

    def _search() -> List[Any]:
        """One DuckDuckGo HTML search attempt; [] on failure or a bot-check page."""
        try:
            resp = _http.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "us-en"},
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36"
                },
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as exc:
            _logger.debug("peer web search failed: %s", exc)
            return []
        soup = BeautifulSoup(resp.content, "html.parser")
        return soup.find_all("div", class_="result")[:8]

    # DuckDuckGo's keyless HTML endpoint occasionally serves a bot-check page
    # (no result divs) instead of real results; one retry with a short
    # backoff recovers most of those without hammering the endpoint.
    results = _search()
    if not results:
        time.sleep(1.5)
        results = _search()
    if not results:
        return []

    symbol_u = symbol.upper()
    candidates: List[str] = []
    for result in results:
        title = result.find("a", class_="result__a")
        snippet = result.find("a", class_="result__snippet")
        text = " ".join(el.get_text(strip=True) for el in (title, snippet) if el)
        for tok in re.findall(r"\b[A-Z]{1,5}\b", text):
            if (
                tok != symbol_u
                and tok not in _TICKER_STOPWORDS
                and tok not in candidates
            ):
                candidates.append(tok)
    if not candidates:
        return []
    candidates = candidates[:15]

    import yfinance as yf_module  # local import: keep module load light

    def _is_plausible_peer(cand: str) -> bool:
        try:
            info = yf_module.Ticker(cand).info or {}
            if not info.get("marketCap"):
                return False
            if sector and info.get("sector") and info.get("sector") != sector:
                return False
            return True
        except Exception:
            return False

    validated: set = set()
    with ThreadPoolExecutor(max_workers=min(len(candidates), 5)) as ex:
        futures = {ex.submit(_is_plausible_peer, c): c for c in candidates}
        for fut in as_completed(futures):
            if fut.result():
                validated.add(futures[fut])

    # Preserve search-result relevance order rather than futures-completion order.
    return [c for c in candidates if c in validated][:limit]


# Enterprise value should sit within hailing distance of market cap for an
# ordinary operating company. yfinance reported SAP's EV as $3,420bn against a
# $249bn market cap — a currency scaling error — which produced an EV/EBITDA of
# 290.8x. Printed in a comparables table beside IBM at 16.8x, one figure like
# that discredits every other number on the page.
_EV_TO_MCAP_MAX = 5.0
_EV_EBITDA_MAX = 100.0


def _sane_ev_ebitda(info: Dict[str, Any]) -> Optional[float]:
    """EV/EBITDA, or None when the inputs fail a basic identity check."""
    ratio = _num(info.get("enterpriseToEbitda"), 1)
    if ratio is None or not 0 < ratio < _EV_EBITDA_MAX:
        return None
    ev, mcap = _num(info.get("enterpriseValue")), _num(info.get("marketCap"))
    if ev and mcap and mcap > 0 and ev / mcap > _EV_TO_MCAP_MAX:
        _logger.debug(
            "implausible EV %.0f vs market cap %.0f; dropping EV/EBITDA", ev, mcap
        )
        return None
    return ratio


def _key_metrics(
    sym: str, info: Optional[Dict[str, Any]] = None, yf_module: Any = None
) -> Optional[Dict[str, Any]]:
    """Key valuation/size metrics for a single symbol from ``ticker.info``.

    Shared by `summarize_peers` (peer-comparison table) and the web UI's
    stock-comparison endpoint. Returns None when the symbol has no market cap
    (i.e. not a valid/tradeable equity), never raises.
    """
    if yf_module is None:
        import yfinance as yf_module  # type: ignore[no-redef]
    try:
        if info is None:
            info = yf_module.Ticker(sym).info or {}
        if not info.get("marketCap"):
            return None
        return {
            "symbol": sym.upper(),
            "name": (info.get("shortName") or info.get("longName") or sym)[:28],
            "current_price": _num(
                info.get("currentPrice") or info.get("regularMarketPrice"), 2
            ),
            "market_cap_b": round(info["marketCap"] / 1e9, 1),
            "pe_ttm": _num(info.get("trailingPE"), 1),
            "fwd_pe": _num(info.get("forwardPE"), 1),
            "beta": _num(info.get("beta"), 2),
            "low_52w": _num(info.get("fiftyTwoWeekLow"), 2),
            "high_52w": _num(info.get("fiftyTwoWeekHigh"), 2),
            "revenue_growth_pct": (
                round(v * 100, 1)
                if (v := _num(info.get("revenueGrowth"))) is not None
                else None
            ),
            "operating_margin_pct": (
                round(v * 100, 1)
                if (v := _num(info.get("operatingMargins"))) is not None
                else None
            ),
            # The three multiples a reviewer specifically asked for and which
            # nothing computed, so the models asserted them from their own
            # knowledge instead — right for IBM as it happens (16.8x), but
            # unsourced and unverifiable. All three are already in `info`.
            # Carried so a candidate peer can be sanity-checked against the
            # subject's line of business before it reaches a comparables table.
            "sector": info.get("sector") or None,
            "industry": info.get("industry") or None,
            "ev_to_ebitda": _sane_ev_ebitda(info),
            "peg": _num(info.get("trailingPegRatio"), 2),
            "fcf_yield_pct": (
                round(fcf / info["marketCap"] * 100, 1)
                if (fcf := _num(info.get("freeCashflow"))) and info.get("marketCap")
                else None
            ),
        }
    except Exception as exc:
        _logger.debug("key metrics failed for %s: %s", sym, exc)
        return None


# How far a candidate may sit from the subject on each axis before it stops
# being a comparable. Expressed as penalties on a log-size distance, so they
# trade off against each other rather than acting as gates.
_DIFFERENT_INDUSTRY_PENALTY = 1.0
_DIFFERENT_SECTOR_PENALTY = 2.5


def select_comparables(
    rows: List[Dict[str, Any]], limit: int = 4
) -> List[Dict[str, Any]]:
    """Rank candidates by how comparable they actually are to the subject.

    A provider's "peers" list is not a comparables set. FMP returns Micron for
    IBM — memory semiconductors against enterprise IT services — ranked by
    market capitalisation, so taking the largest names puts the least similar
    business at the top of the table.

    Scoring rather than filtering, because both hard gates fail. Rank by size
    alone and Micron leads. Gate on industry alone and IBM is compared with
    EPAM at $5.5bn against its own $224bn, while SAP and Cisco — far closer in
    size and plainly comparable businesses — are excluded over a yfinance
    label. The score is distance in log market cap plus a penalty for a
    different industry and a larger one for a different sector, so a same-
    industry peer wins at comparable size but a forty-fold size gap does not
    survive being in the right industry.
    """
    subject = next((r for r in rows if r.get("is_subject")), None)
    if not subject:
        return list(rows)[:limit]

    import math

    base = subject.get("market_cap_b") or 0
    sector, industry = subject.get("sector"), subject.get("industry")

    def score(r: Dict[str, Any]) -> float:
        mcap = r.get("market_cap_b") or 0
        # Log scale: comparability is a matter of order of magnitude, and a raw
        # difference would call $440bn and $5bn equally distant from $224bn.
        dist = abs(math.log(mcap / base)) if base > 0 and mcap > 0 else 3.0
        if industry and r.get("industry") != industry:
            dist += _DIFFERENT_INDUSTRY_PENALTY
        if sector and r.get("sector") != sector:
            dist += _DIFFERENT_SECTOR_PENALTY
        return dist

    others = sorted((r for r in rows if not r.get("is_subject")), key=score)
    return [subject] + others[:limit]


def summarize_peers(
    symbol: str, yf_module: Any = None, peer_symbols: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Side-by-side key metrics for the subject company and its true business peers.

    ``peer_symbols`` skips discovery when the caller already knows the peer set.
    Discovery is a keyless web search that can legitimately come back empty —
    when it did for IBM the whole metrics table was dropped, and the report
    printed a peer comparison whose every cell read "Not available" while the
    provider chain had supplied a perfectly good peer list.
    """
    if yf_module is None:
        import yfinance as yf_module  # type: ignore[no-redef]

    try:
        subject_info = yf_module.Ticker(symbol).info or {}
    except Exception as exc:
        _logger.debug("subject info fetch failed for peers: %s", exc)
        subject_info = {}

    peers = peer_symbols or fetch_peer_symbols(
        symbol,
        company_name=subject_info.get("shortName") or subject_info.get("longName"),
        sector=subject_info.get("sector"),
        industry=subject_info.get("industry"),
    )
    if not peers:
        return {}

    rows = []
    subject_row = _key_metrics(symbol, info=subject_info, yf_module=yf_module)
    if subject_row:
        subject_row["is_subject"] = True
        rows.append(subject_row)
    for sym in peers:
        row = _key_metrics(sym, yf_module=yf_module)
        if row:
            row["is_subject"] = False
            rows.append(row)
    return {"rows": rows} if len(rows) >= 2 else {}


# ── Catalysts (upcoming events) ──────────────────────────────────────────────


def summarize_catalysts(ticker: Any) -> Dict[str, Any]:
    """Next earnings date with street estimates, plus dividend dates."""
    out: Dict[str, Any] = {}
    try:
        cal = ticker.calendar or {}
        if not isinstance(cal, dict):
            return out
        ed = cal.get("Earnings Date")
        if ed:
            first = ed[0] if isinstance(ed, (list, tuple)) else ed
            out["next_earnings_date"] = _date_label(first)
        if cal.get("Earnings Average") is not None:
            out["earnings_eps_estimate"] = _num(cal.get("Earnings Average"), 2)
        if cal.get("Revenue Average"):
            out["earnings_revenue_estimate_m"] = _millions(cal.get("Revenue Average"))
        for key, label in (
            ("Ex-Dividend Date", "ex_dividend_date"),
            ("Dividend Date", "dividend_date"),
        ):
            if cal.get(key):
                out[label] = _date_label(cal[key])
    except Exception as exc:
        _logger.debug("calendar failed: %s", exc)
    return out


# ── Valuation scenarios (two-stage DCF per share) ────────────────────────────


# Minimum gap between the discount rate and terminal growth. Below this the
# Gordon residual dominates the valuation and the answer stops being a forecast.
_MIN_WACC_TERMINAL_SPREAD_PCT = 5.0


def wacc_pct(
    beta: Optional[float],
    market_cap_m: Optional[float],
    total_debt_m: Optional[float],
    risk_free_pct: float = 4.0,
    equity_risk_premium_pct: float = 5.0,
    credit_spread_pct: float = 1.5,
    tax_rate: float = 0.21,
) -> float:
    """Weighted average cost of capital from CAPM, with disclosed assumptions.

    Derived rather than asserted, because the previous scenario grid simply
    declared 12% / 10% / 9% and tied the *lowest* discount rate to the *highest*
    growth rate. That double-counts optimism in the bull case and pessimism in
    the bear case, which is how a grid could sit entirely below the traded price
    for a profitable compounder.
    """
    b = beta if isinstance(beta, (int, float)) and beta > 0 else 1.0
    cost_equity = risk_free_pct + b * equity_risk_premium_pct
    e = market_cap_m if isinstance(market_cap_m, (int, float)) and market_cap_m else 0.0
    d = total_debt_m if isinstance(total_debt_m, (int, float)) and total_debt_m else 0.0
    if e + d <= 0:
        return round(cost_equity, 2)
    cost_debt_after_tax = (risk_free_pct + credit_spread_pct) * (1 - tax_rate)
    return round((e * cost_equity + d * cost_debt_after_tax) / (e + d), 2)


def fcf_dcf_scenarios(
    fcf_m: Optional[float],
    shares_m: Optional[float],
    net_debt_m: float = 0.0,
    base_wacc_pct: Optional[float] = None,
    growth_pct: Optional[float] = None,
    terminal_pct: float = 2.5,
    high_growth_years: int = 5,
    fade_years: int = 5,
) -> List[Dict[str, Any]]:
    """Bear/base/bull equity value per share from unlevered free cash flow.

    Replaces an EPS-stream model that was labelled a DCF but discounted
    earnings, ignored the balance sheet, and never divided by a share count.
    Here: free cash flow grows for ``high_growth_years``, fades linearly to the
    terminal rate over ``fade_years``, then a Gordon terminal value; the sum is
    enterprise value, from which net debt is subtracted to reach equity value,
    divided by shares outstanding.

    Scenarios vary *growth* as the primary lever and move the discount rate only
    slightly for risk, so the bear case is not penalised twice.
    """
    if not fcf_m or fcf_m <= 0 or not shares_m or shares_m <= 0:
        return []
    g0 = 8.0 if growth_pct is None else float(growth_pct)
    g0 = max(-10.0, min(g0, 25.0))  # consensus growth is not a forever rate
    wacc = float(base_wacc_pct) if base_wacc_pct else 9.0

    # A Gordon terminal value is 1/(WACC - g), so a narrow spread explodes it:
    # a low-beta name discounting at 6.9% against 2.5% terminal growth implies a
    # ~23x exit multiple and a base case 38% above the traded price. Requiring at
    # least MIN_SPREAD between the two caps the implied terminal multiple near
    # 20x, which keeps the model honest about how much of the value is a
    # residual guess rather than forecast cash.
    min_disc = terminal_pct + _MIN_WACC_TERMINAL_SPREAD_PCT

    variants = [
        ("Bear", g0 * 0.4, wacc + 1.0),
        ("Base", g0, wacc),
        ("Bull", min(g0 * 1.4, 30.0), wacc - 0.5),
    ]
    out: List[Dict[str, Any]] = []
    for name, g_pct, disc_pct in variants:
        disc_pct = max(disc_pct, min_disc)
        disc, term = disc_pct / 100.0, terminal_pct / 100.0
        if disc <= term:
            continue
        g = g_pct / 100.0
        flows, f = [], float(fcf_m)
        for yr in range(1, high_growth_years + fade_years + 1):
            if yr <= high_growth_years:
                rate = g
            else:
                # Linear glide from the scenario rate to terminal.
                step = (yr - high_growth_years) / float(fade_years)
                rate = g + (term - g) * step
            f *= 1 + rate
            flows.append(f)
        pv = sum(cf / (1 + disc) ** (i + 1) for i, cf in enumerate(flows))
        tv = flows[-1] * (1 + term) / (disc - term)
        ev = pv + tv / (1 + disc) ** len(flows)
        equity = ev - (net_debt_m or 0.0)
        out.append(
            {
                "scenario": name,
                "growth_pct": round(g_pct, 1),
                "discount_pct": round(disc_pct, 2),
                "terminal_pct": terminal_pct,
                "enterprise_value_m": round(ev, 1),
                "net_debt_m": round(net_debt_m or 0.0, 1),
                "intrinsic_per_share": round(max(equity, 0.0) / shares_m, 2),
                "method": (
                    f"unlevered FCF, {high_growth_years}y growth + "
                    f"{fade_years}y fade to {terminal_pct}%, WACC {disc_pct:.2f}%"
                ),
            }
        )
    return out


def dcf_scenarios(eps_base: float, growth_pct: float) -> List[Dict[str, Any]]:
    """Bear/base/bull intrinsic-value-per-share grid with disclosed assumptions.

    Two-stage model: 3 years at the scenario growth rate, 2 years fading to the
    terminal rate, Gordon terminal value. Same math as ValuationCalculatorTool.
    """
    if not eps_base or eps_base <= 0:
        return []
    base_g = max(0.0, min(float(growth_pct), 30.0)) / 100.0
    scenarios = [
        ("Bear", base_g * 0.5, 0.12),
        ("Base", base_g, 0.10),
        ("Bull", min(base_g * 1.25, 0.35), 0.09),
    ]
    terminal = 0.025
    out = []
    for name, g, disc in scenarios:
        if disc <= terminal:
            continue
        earnings = []
        e = float(eps_base)
        for year in range(1, 6):
            e = e * (1 + (g if year <= 3 else terminal))
            earnings.append(e)
        pv = sum(e / (1 + disc) ** (i + 1) for i, e in enumerate(earnings))
        tv = earnings[-1] * (1 + terminal) / (disc - terminal)
        pv_tv = tv / (1 + disc) ** 5
        out.append(
            {
                "scenario": name,
                "growth_pct": round(g * 100, 1),
                "discount_pct": round(disc * 100, 1),
                "terminal_pct": round(terminal * 100, 1),
                "intrinsic_per_share": round(pv + pv_tv, 2),
            }
        )
    return out


# ── Google Trends search interest ────────────────────────────────────────────


def summarize_search_interest(symbol: str) -> Dict[str, Any]:
    """Retail attention momentum from Google Trends (pytrends, best-effort)."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return {}
    try:
        keyword = f"{symbol.upper()} stock"
        pt = TrendReq(hl="en-US", tz=0, timeout=(5, 10))
        pt.build_payload([keyword], timeframe="today 3-m")
        df = pt.interest_over_time()
        if df is None or df.empty:
            return {}
        series = df[keyword]
        latest_week = float(series.iloc[-7:].mean())
        avg_3m = float(series.mean())
        return {
            "keyword": keyword,
            "latest_week_avg": round(latest_week, 1),
            "three_month_avg": round(avg_3m, 1),
            "momentum_pct": (
                round((latest_week - avg_3m) / avg_3m * 100, 1) if avg_3m else None
            ),
            "source": "google_trends",
        }
    except Exception as exc:
        _logger.debug("google trends failed: %s", exc)
        return {}
