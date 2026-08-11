"""Side-by-side comparison of 2-4 arbitrary symbols — key stats, analyst
consensus, and (when available) sentiment/valuation from an existing report.
Works for symbols that have never been analyzed: metrics are fetched live."""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import yfinance as yf
from fastapi import APIRouter

from ...symbols import safe_symbol
from ...tools.cache import get_cached, set_cached
from ...tools.yf_summaries import _key_metrics, summarize_analyst_data
from .. import _paths
from ..price_series import DEFAULT_PERIOD, MAX_SYMBOLS, fetch_price_series

router = APIRouter(prefix="/api/compare", tags=["compare"])

_METRICS_CACHE_TTL = 900  # 15 min


def _report_overlay(symbol: str) -> Dict[str, Any]:
    """Pull sentiment/valuation extras from an existing chart_data.json, if
    this symbol has already been analyzed. Best-effort — never raises."""
    path = _paths.chart_path(symbol)
    if path is None or not path.exists():
        return {
            "has_report": False,
            "sentiment_snapshot": None,
            "valuation_scenarios": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "has_report": True,
            "sentiment_snapshot": data.get("sentiment_snapshot"),
            "valuation_scenarios": data.get("valuation_scenarios"),
        }
    except Exception:
        return {
            "has_report": True,
            "sentiment_snapshot": None,
            "valuation_scenarios": None,
        }


def _fetch_one(symbol: str) -> Optional[Dict[str, Any]]:
    """Live key stats + analyst consensus for one symbol. None if the symbol
    isn't a valid/tradeable equity (no market cap)."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
    except Exception:
        info = {}
    key_stats = _key_metrics(symbol, info=info)
    if key_stats is None:
        return None
    try:
        analyst = summarize_analyst_data(ticker)
    except Exception:
        analyst = {}
    return {
        "symbol": symbol,
        "key_stats": key_stats,
        "analyst": analyst,
        **_report_overlay(symbol),
    }


def _dedupe_symbols(symbols: List[str]) -> List[str]:
    seen: List[str] = []
    for s in symbols:
        valid = safe_symbol(s)
        if valid and valid not in seen:
            seen.append(valid)
    return seen


@router.get("/metrics")
def compare_metrics(symbols: str) -> Dict[str, Any]:
    """Key stats + analyst consensus for up to MAX_SYMBOLS symbols, fetched
    live and in parallel. Invalid/untradeable symbols are omitted, not
    errored — a typo shouldn't sink a comparison of otherwise-good tickers."""
    requested = [s for s in symbols.split(",") if s.strip()]
    valid = _dedupe_symbols(requested)
    omitted = [s for s in requested if safe_symbol(s) not in valid]
    valid = valid[:MAX_SYMBOLS]

    cache_key = json.dumps(sorted(valid))
    cached = get_cached("compare_metrics", cache_key)
    if cached is not None:
        return cached

    with ThreadPoolExecutor(max_workers=max(1, len(valid))) as ex:
        results = list(ex.map(_fetch_one, valid))

    rows = []
    for sym, row in zip(valid, results):
        if row is None:
            omitted.append(sym)
        else:
            rows.append(row)

    result = {"symbols": rows, "omitted": omitted}
    set_cached("compare_metrics", cache_key, result, _METRICS_CACHE_TTL)
    return result


@router.get("/prices")
def compare_prices(symbols: str, period: str = DEFAULT_PERIOD) -> Dict[str, Any]:
    """Price series for the comparison page's indexed multi-line chart —
    thin wrapper over the same helper the report Overview chart uses."""
    requested = [s for s in symbols.split(",") if s.strip()]
    return fetch_price_series(requested, period)
