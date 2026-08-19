"""Alpaca market-data client — bars with honest session semantics.

Requires ``ALPACA_API_KEY`` and ``ALPACA_API_SECRET``; the router only
instantiates this class when both are set.

What it adds that the existing price chain does not: **a settled previous
close, stated as such.** yfinance's ``history()`` returns today's bar while the
session is running, so its last "close" is a live quote that keeps moving — a
report generated at 11:27 ET said IBM "closed at $237.45 on August 19" with the
market open and the price $236.53 an hour later. Alpaca's snapshot endpoint
distinguishes ``dailyBar`` (today, in progress) from ``prevDailyBar`` (the last
completed session), so the distinction comes from the data rather than from
inferring it against a market calendar.

Fundamentals, estimates and filings are not offered here; those stay as the
``ProviderBase`` no-ops so the router falls through to FMP/yfinance.

Note the free tier serves IEX-sourced data, which can differ marginally from
consolidated SIP prints. That is immaterial for a research note quoting a
close to the cent, but it is why this is a price source and not an audit trail.
"""

import logging
from typing import Any, Dict, List

from .. import _http
from . import base

_logger = logging.getLogger(__name__)

_BASE_URL = "https://data.alpaca.markets/v2"


class AlpacaProvider(base.ProviderBase):
    name = "alpaca"

    def __init__(self, api_key: str, api_secret: str, feed: str = "iex") -> None:
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
        }
        # Without an explicit feed the API assumes SIP, which a free key may
        # not read: bars return 403 "subscription does not permit querying
        # recent SIP data" while the snapshot endpoint happens to succeed, so
        # it looks like a broken bars call rather than a plan limit.
        self._feed = feed or "iex"

    def _get(self, path: str, **params: Any) -> Any:
        params.setdefault("feed", self._feed)
        resp = _http.get(
            f"{_BASE_URL}{path}", params=params, headers=self._headers, timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get(f"/stocks/{symbol}/snapshot") or {}
            day = data.get("dailyBar") or {}
            prev = data.get("prevDailyBar") or {}
            price = day.get("c") or (data.get("latestTrade") or {}).get("p")
            prev_close = prev.get("c")
            if price is None:
                return {}
            return {
                "symbol": symbol,
                "price": price,
                "previous_close": prev_close,
                "change_pct": (
                    round((price - prev_close) / prev_close * 100, 2)
                    if prev_close
                    else None
                ),
                "volume": day.get("v"),
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning("Alpaca get_quote failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_last_close(self, symbol: str) -> Dict[str, Any]:
        """The most recent *completed* session's close, with its date.

        Outside the Protocol's eight capabilities, like Polygon's batch quotes.
        The snapshot labels the previous session for us, so no market calendar
        or timezone arithmetic is needed to know whether today's bar has
        settled — the distinction the report's "last close" wording depends on.
        """
        try:
            data = self._get(f"/stocks/{symbol}/snapshot") or {}
            prev = data.get("prevDailyBar") or {}
            close, stamp = prev.get("c"), prev.get("t")
            if close is None or not stamp:
                return {}
            return {
                "symbol": symbol,
                "price": round(float(close), 2),
                # Timestamps are RFC-3339; the session date is the date part.
                "date": str(stamp)[:10],
                "basis": "last close",
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning("Alpaca get_last_close failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_daily_bars(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        try:
            bars: List[Dict[str, Any]] = []
            page: Any = None
            while True:
                params: Dict[str, Any] = {
                    "timeframe": "1Day",
                    "start": start,
                    "end": end,
                    "adjustment": "all",
                    "limit": 10000,
                }
                if page:
                    params["page_token"] = page
                data = self._get(f"/stocks/{symbol}/bars", **params) or {}
                for r in data.get("bars") or []:
                    bars.append(
                        {
                            "date": str(r.get("t"))[:10],
                            "open": r.get("o"),
                            "high": r.get("h"),
                            "low": r.get("l"),
                            "close": r.get("c"),
                            "volume": r.get("v"),
                        }
                    )
                page = data.get("next_page_token")
                if not page:
                    break
            if not bars:
                return {}
            return {"symbol": symbol, "bars": bars, "source": self.name}
        except Exception as exc:
            _logger.warning("Alpaca get_daily_bars failed for %s: %s", symbol, exc)
            return {"error": str(exc)}
