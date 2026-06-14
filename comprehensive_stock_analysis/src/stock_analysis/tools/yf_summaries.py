"""Compact summarizers over a yfinance Ticker.

Each function takes an already-constructed ``yf.Ticker`` and returns a small,
JSON-serializable dict (top-N lists, latest values, deltas — never raw frames)
sized to fit comfortably in an LLM prompt. Every accessor is guarded: a missing
or failing yfinance property yields a partial dict, never an exception.

Sharing one Ticker across all summarizers minimizes Yahoo Finance API calls.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from . import _http

_logger = logging.getLogger(__name__)


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


def _date_label(col: Any) -> str:
    try:
        return col.date().isoformat()
    except Exception:
        return str(col)[:10]


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
                round((mean - current) / current * 100, 1)
                if mean and current else None
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
            recent = ud[ud.index >= pd.Timestamp(cutoff)] if hasattr(ud.index, "tz") else ud
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
            entry = {k: _num(row.get(src)) for k, src in zip(
                ("avg", "low", "high", "year_ago", "analysts", "growth_pct"),
                value_keys,
            ) if src in row.index}
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
                        round(g * 100, 1) if (g := _num(row.get("growth"))) is not None else None
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
                    round(v * 100, 2) if (v := _num(breakdown.get("insidersPercentHeld"))) is not None else None
                ),
                "institution_pct": (
                    round(v * 100, 2) if (v := _num(breakdown.get("institutionsPercentHeld"))) is not None else None
                ),
                "institution_count": _num(breakdown.get("institutionsCount"), 0),
            }
    except Exception as exc:
        _logger.debug("major_holders failed: %s", exc)

    try:
        ih = ticker.institutional_holders
        if ih is not None and not ih.empty:
            out["top_institutions"] = [
                {
                    "holder": str(r.get("Holder", "")),
                    "pct_held": (
                        round(v * 100, 2) if (v := _num(r.get("pctHeld"))) is not None else None
                    ),
                    "value_usd_m": _millions(r.get("Value")),
                }
                for r in ih.head(8).to_dict("records")
            ]
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
                kind = "sell" if "sale" in text else ("buy" if ("purchase" in text or "buy" in text) else "other")
                if kind == "buy":
                    buys += 1
                elif kind == "sell":
                    sells += 1
                txns.append({
                    "date": _date_label(r.get("Start Date")),
                    "insider": str(r.get("Insider", "")),
                    "position": str(r.get("Position", "")),
                    "type": kind,
                    "shares": _num(r.get("Shares"), 0),
                    "value_usd_m": _millions(r.get("Value")),
                })
            out["insider_transactions"] = txns
            out["insider_recent_summary"] = {"buys": buys, "sells": sells, "sampled": len(txns)}
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
            op = _row(inc, ["Operating Income", "OperatingIncome", "Total Operating Income As Reported"])
            net = _row(inc, ["Net Income", "Net Income Common Stockholders", "NetIncome"])
            annual: Dict[str, Any] = {}
            for i, col in enumerate(cols[:3]):
                label = _date_label(col)
                rev_v = _millions(revenue.get(col)) if revenue is not None else None
                prev_v = (
                    _millions(revenue.get(cols[i + 1]))
                    if revenue is not None and i + 1 < len(cols) else None
                )
                annual[label] = {
                    "revenue_m": rev_v,
                    "gross_profit_m": _millions(gross.get(col)) if gross is not None else None,
                    "operating_income_m": _millions(op.get(col)) if op is not None else None,
                    "net_income_m": _millions(net.get(col)) if net is not None else None,
                    "revenue_yoy_pct": (
                        round((rev_v - prev_v) / abs(prev_v) * 100, 1)
                        if rev_v is not None and prev_v else None
                    ),
                }
            out["annual_income"] = annual
    except Exception as exc:
        _logger.debug("income_stmt failed: %s", exc)

    try:
        bs = ticker.balance_sheet
        if bs is not None and not bs.empty:
            cols = list(bs.columns)[:2]
            assets = _row(bs, ["Total Assets", "TotalAssets"])
            cash = _row(bs, ["Cash Cash Equivalents And Short Term Investments",
                             "Cash And Cash Equivalents", "Cash Financial"])
            debt = _row(bs, ["Total Debt", "TotalDebt"])
            equity = _row(bs, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"])
            out["balance_sheet"] = {
                _date_label(col): {
                    "total_assets_m": _millions(assets.get(col)) if assets is not None else None,
                    "cash_and_sti_m": _millions(cash.get(col)) if cash is not None else None,
                    "total_debt_m": _millions(debt.get(col)) if debt is not None else None,
                    "stockholders_equity_m": _millions(equity.get(col)) if equity is not None else None,
                }
                for col in cols
            }
    except Exception as exc:
        _logger.debug("balance_sheet failed: %s", exc)

    try:
        cf = ticker.cashflow
        if cf is not None and not cf.empty:
            cols = list(cf.columns)[:3]
            ocf = _row(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
            capex = _row(cf, ["Capital Expenditure", "CapitalExpenditure"])
            fcf = _row(cf, ["Free Cash Flow", "FreeCashFlow"])
            buyback = _row(cf, ["Repurchase Of Capital Stock"])
            divs = _row(cf, ["Cash Dividends Paid", "Common Stock Dividend Paid"])
            out["cash_flow"] = {
                _date_label(col): {
                    "operating_cf_m": _millions(ocf.get(col)) if ocf is not None else None,
                    "capex_m": _millions(capex.get(col)) if capex is not None else None,
                    "free_cash_flow_m": _millions(fcf.get(col)) if fcf is not None else None,
                    "buybacks_m": _millions(buyback.get(col)) if buyback is not None else None,
                    "dividends_paid_m": _millions(divs.get(col)) if divs is not None else None,
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
            # 5-year dividend CAGR from annual sums
            annual = d.groupby(d.index.year).sum()
            if len(annual) >= 6:
                first, last = float(annual.iloc[-6]), float(annual.iloc[-1])
                if first > 0:
                    out["dividend_cagr_5y_pct"] = round(((last / first) ** 0.2 - 1) * 100, 1)
    except Exception as exc:
        _logger.debug("dividends failed: %s", exc)
    try:
        s = ticker.splits
        if s is not None and len(s) > 0:
            out["last_split"] = {"date": _date_label(s.index[-1]), "ratio": _num(s.iloc[-1])}
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
                k: round(float(v) * 100, 2) for k, v in sw.items() if _num(v) is not None
            }
    except Exception as exc:
        _logger.debug("sector_weightings failed: %s", exc)
    try:
        ac = fd.asset_classes
        if ac:
            out["asset_classes_pct"] = {
                k: round(float(v) * 100, 2) for k, v in ac.items() if _num(v) is not None
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

def fetch_peer_symbols(symbol: str, limit: int = 4) -> List[str]:
    """Similar symbols from Yahoo's keyless recommendations endpoint."""
    try:
        resp = _http.get(
            f"https://query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/{symbol.upper()}",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36"},
            timeout=10,
        )
        resp.raise_for_status()
        recs = resp.json()["finance"]["result"][0]["recommendedSymbols"]
        return [r["symbol"] for r in recs[:limit]]
    except Exception as exc:
        _logger.debug("peer symbols fetch failed: %s", exc)
        return []


def summarize_peers(symbol: str, yf_module: Any = None) -> Dict[str, Any]:
    """Side-by-side key metrics for the subject company and its peers."""
    if yf_module is None:
        import yfinance as yf_module  # type: ignore[no-redef]

    peers = fetch_peer_symbols(symbol)
    if not peers:
        return {}

    def _metrics(sym: str) -> Optional[Dict[str, Any]]:
        try:
            info = yf_module.Ticker(sym).info or {}
            if not info.get("marketCap"):
                return None
            return {
                "symbol": sym.upper(),
                "name": (info.get("shortName") or info.get("longName") or sym)[:28],
                "market_cap_b": round(info["marketCap"] / 1e9, 1),
                "pe_ttm": _num(info.get("trailingPE"), 1),
                "fwd_pe": _num(info.get("forwardPE"), 1),
                "revenue_growth_pct": (
                    round(v * 100, 1) if (v := _num(info.get("revenueGrowth"))) is not None else None
                ),
                "operating_margin_pct": (
                    round(v * 100, 1) if (v := _num(info.get("operatingMargins"))) is not None else None
                ),
            }
        except Exception as exc:
            _logger.debug("peer metrics failed for %s: %s", sym, exc)
            return None

    rows = []
    for sym in [symbol.upper()] + peers:
        row = _metrics(sym)
        if row:
            row["is_subject"] = sym.upper() == symbol.upper()
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
        for key, label in (("Ex-Dividend Date", "ex_dividend_date"),
                           ("Dividend Date", "dividend_date")):
            if cal.get(key):
                out[label] = _date_label(cal[key])
    except Exception as exc:
        _logger.debug("calendar failed: %s", exc)
    return out


# ── Valuation scenarios (two-stage DCF per share) ────────────────────────────

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
        out.append({
            "scenario": name,
            "growth_pct": round(g * 100, 1),
            "discount_pct": round(disc * 100, 1),
            "terminal_pct": round(terminal * 100, 1),
            "intrinsic_per_share": round(pv + pv_tv, 2),
        })
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
            "momentum_pct": round((latest_week - avg_3m) / avg_3m * 100, 1) if avg_3m else None,
            "source": "google_trends",
        }
    except Exception as exc:
        _logger.debug("google trends failed: %s", exc)
        return {}
