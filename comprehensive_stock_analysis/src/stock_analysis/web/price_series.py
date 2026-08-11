"""Shared live price-series fetch for the report Overview chart and the
stock-comparison page. Both consumers need "N symbols, one period, from
today back" — this is the one place that logic lives."""

import json
from datetime import date, timedelta
from typing import Any, Dict, List

from ..symbols import safe_symbol
from ..tools.cache import get_cached, set_cached
from ..tools.providers import ROUTER

MAX_SYMBOLS = 4
_CACHE_TTL = 900  # 15 min — bounds repeated Yahoo/Polygon calls on rapid UI toggling

_PERIOD_DAYS = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "5y": 1825}
DEFAULT_PERIOD = "1y"


def _normalize_period(period: str) -> str:
    return period if period in _PERIOD_DAYS else DEFAULT_PERIOD


def _dedupe_symbols(symbols: List[str]) -> List[str]:
    seen: List[str] = []
    for s in symbols:
        valid = safe_symbol(s)
        if valid and valid not in seen:
            seen.append(valid)
    return seen


def fetch_price_series(symbols: List[str], period: str) -> Dict[str, Any]:
    """Fetch daily-bar close-price series for up to MAX_SYMBOLS symbols.

    Invalid/duplicate symbols are silently dropped into `omitted`. A symbol
    the provider chain can't serve (capability gap or failure) is also
    omitted, never a hard error for the whole request — one bad ticker
    shouldn't break a chart showing three good ones.
    """
    period = _normalize_period(period)
    valid = _dedupe_symbols(symbols)
    omitted = [s for s in symbols if safe_symbol(s) not in valid]
    valid = valid[:MAX_SYMBOLS]

    cache_key = json.dumps({"symbols": valid, "period": period}, sort_keys=True)
    cached = get_cached("chart_prices", cache_key)
    if cached is not None:
        return cached

    end = date.today()
    start = end - timedelta(days=_PERIOD_DAYS[period])
    series = []
    for sym in valid:
        bars = ROUTER.get_daily_bars(sym, start.isoformat(), end.isoformat())
        if not bars or "error" in bars or not bars.get("bars"):
            omitted.append(sym)
            continue
        series.append(
            {
                "symbol": sym,
                "bars": [
                    {"date": b["date"], "close": b["close"]}
                    for b in bars["bars"]
                    if b.get("close") is not None
                ],
            }
        )

    result = {"period": period, "series": series, "omitted": omitted}
    set_cached("chart_prices", cache_key, result, _CACHE_TTL)
    return result
