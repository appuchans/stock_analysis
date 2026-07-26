"""The universal, keyless fallback provider — thin wrappers over the existing
``yf_summaries`` functions and ``yfinance`` itself. Every method here is what
already powers the flow pipeline; the provider layer just gives it the same
shape as the premium providers so the router can treat them interchangeably.
"""

import logging
from typing import Any, Dict

from . import base

_logger = logging.getLogger(__name__)


class YFinanceProvider(base.ProviderBase):
    name = "yfinance"

    def _ticker(self, symbol: str):
        import yfinance as yf

        return yf.Ticker(symbol)

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            t = self._ticker(symbol)
            fast = t.fast_info
            price = getattr(fast, "last_price", None)
            prev_close = getattr(fast, "previous_close", None)
            change_pct = (
                ((price - prev_close) / prev_close * 100)
                if price is not None and prev_close else None
            )
            return {
                "symbol": symbol,
                "price": price,
                "previous_close": prev_close,
                "change_pct": change_pct,
                "volume": getattr(fast, "last_volume", None),
                "source": self.name,
            }
        except Exception as exc:
            _logger.debug("yfinance get_quote failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_daily_bars(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        try:
            hist = self._ticker(symbol).history(start=start, end=end, interval="1d")
            if hist is None or hist.empty:
                return {}
            bars = [
                {
                    "date": idx.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else None,
                }
                for idx, row in hist.iterrows()
            ]
            return {"symbol": symbol, "bars": bars, "source": self.name}
        except Exception as exc:
            _logger.debug("yfinance get_daily_bars failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_statements(self, symbol: str, years: int = 10) -> Dict[str, Any]:
        # yfinance only exposes ~3-4 fiscal years — a real gap this fallback
        # cannot close; FMP (when keyed) is what actually reaches `years`.
        try:
            from ..yf_summaries import summarize_financial_statements

            result = summarize_financial_statements(self._ticker(symbol))
            if result:
                result["source"] = self.name
            return result
        except Exception as exc:
            _logger.debug("yfinance get_statements failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_estimates(self, symbol: str) -> Dict[str, Any]:
        try:
            from ..yf_summaries import summarize_analyst_data

            result = summarize_analyst_data(self._ticker(symbol))
            if result:
                result["source"] = self.name
            return result
        except Exception as exc:
            _logger.debug("yfinance get_estimates failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_transcript(self, symbol: str) -> Dict[str, Any]:
        # No transcript data available keyless — a genuine capability gap.
        return {}

    def get_insider_trades(self, symbol: str) -> Dict[str, Any]:
        try:
            from ..yf_summaries import summarize_ownership

            result = summarize_ownership(self._ticker(symbol))
            if result:
                result["source"] = self.name
            return result
        except Exception as exc:
            _logger.debug("yfinance get_insider_trades failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_calendar(self, symbol: str) -> Dict[str, Any]:
        try:
            from ..yf_summaries import summarize_catalysts

            result = summarize_catalysts(self._ticker(symbol))
            if result:
                result["source"] = self.name
            return result
        except Exception as exc:
            _logger.debug("yfinance get_calendar failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_etf_holdings(self, symbol: str) -> Dict[str, Any]:
        try:
            from ..yf_summaries import summarize_etf_portfolio

            result = summarize_etf_portfolio(self._ticker(symbol))
            if result:
                result["source"] = self.name
            return result
        except Exception as exc:
            _logger.debug("yfinance get_etf_holdings failed for %s: %s", symbol, exc)
            return {"error": str(exc)}
