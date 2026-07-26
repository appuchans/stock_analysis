"""Polygon.io client — the premium price/market-data provider.

Requires ``POLYGON_API_KEY``; the router only instantiates this class when
that key is set. Polygon's Stocks Starter tier covers quotes and historical
bars (its main value here: unlimited API calls, unlike yfinance's soft
rate limits, which matters once scheduled polling exists) but not
fundamentals/estimates/transcripts — those capabilities are left as the
``ProviderBase`` no-op defaults so the router falls through to FMP/yfinance
for them.
"""

import logging
from typing import Any, Dict

from .. import _http
from . import base

_logger = logging.getLogger(__name__)

_BASE_URL = "https://api.polygon.io"


class PolygonProvider(base.ProviderBase):
    name = "polygon"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _get(self, path: str, **params: Any) -> Any:
        params["apikey"] = self._api_key
        resp = _http.get(f"{_BASE_URL}{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
            ticker = (data or {}).get("ticker") or {}
            day = ticker.get("day") or {}
            prev = ticker.get("prevDay") or {}
            price = day.get("c") or (ticker.get("lastTrade") or {}).get("p")
            prev_close = prev.get("c")
            return {
                "symbol": symbol,
                "price": price,
                "previous_close": prev_close,
                "change_pct": ticker.get("todaysChangePerc"),
                "volume": day.get("v"),
                "source": self.name,
            } if price is not None else {}
        except Exception as exc:
            _logger.warning("Polygon get_quote failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_daily_bars(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        try:
            data = self._get(
                f"/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
                adjusted="true", sort="asc", limit=5000,
            )
            results = (data or {}).get("results") or []
            if not results:
                return {}
            from datetime import datetime, timezone

            bars = [
                {
                    "date": datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "open": r.get("o"), "high": r.get("h"), "low": r.get("l"),
                    "close": r.get("c"), "volume": r.get("v"),
                }
                for r in results
            ]
            return {"symbol": symbol, "bars": bars, "source": self.name}
        except Exception as exc:
            _logger.warning("Polygon get_daily_bars failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_batch_quotes(self, symbols: list) -> Dict[str, Dict[str, Any]]:
        """Multiple symbols in one call — what makes frequent rule-evaluation
        polling (Phase 3) affordable instead of one request per symbol."""
        if not symbols:
            return {}
        try:
            data = self._get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                tickers=",".join(symbols),
            )
            out: Dict[str, Dict[str, Any]] = {}
            for t in (data or {}).get("tickers") or []:
                sym = t.get("ticker")
                day = t.get("day") or {}
                prev = t.get("prevDay") or {}
                price = day.get("c") or (t.get("lastTrade") or {}).get("p")
                if sym and price is not None:
                    out[sym] = {
                        "symbol": sym, "price": price, "previous_close": prev.get("c"),
                        "change_pct": t.get("todaysChangePerc"), "source": self.name,
                    }
            return out
        except Exception as exc:
            _logger.warning("Polygon get_batch_quotes failed: %s", exc)
            return {}
