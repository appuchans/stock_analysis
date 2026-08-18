"""The capability protocol every market-data provider implements.

Each method returns a plain dict — matching every other tool in this codebase
(``yf_summaries``, ``free_data_collection``) — with ``{"error": "..."}`` on
failure so callers can degrade gracefully instead of raising. A provider that
does not support a capability at all (e.g. yfinance has no earnings-call
transcripts) simply returns ``{}``; that is a *capability gap*, not an error,
and the router treats it as "try the next provider in the chain" rather than
logging a failure.
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class MarketDataProvider(Protocol):
    """Capabilities a provider may implement. Not every provider implements
    every method — the router only calls what a given provider class defines
    beyond this Protocol's defaults, checked via ``hasattr``."""

    name: str

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Latest price, day change, volume."""
        ...

    def get_daily_bars(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        """OHLCV series between ISO dates ``start`` and ``end`` (inclusive)."""
        ...

    def get_statements(self, symbol: str, years: int = 10) -> Dict[str, Any]:
        """Multi-year income/balance/cash-flow statements."""
        ...

    def get_estimates(self, symbol: str) -> Dict[str, Any]:
        """Analyst EPS/revenue estimates and revision history."""
        ...

    def get_transcript(self, symbol: str) -> Dict[str, Any]:
        """Summary of the most recent earnings-call transcript."""
        ...

    def get_insider_trades(self, symbol: str) -> Dict[str, Any]:
        """Recent insider buy/sell transactions."""
        ...

    def get_calendar(self, symbol: str) -> Dict[str, Any]:
        """Upcoming earnings / ex-dividend dates."""
        ...

    def get_etf_holdings(self, symbol: str) -> Dict[str, Any]:
        """Sector weightings and top holdings for an ETF."""
        ...

    def get_revenue_segments(self, symbol: str) -> Dict[str, Any]:
        """Revenue split by product line and by geography.

        No keyless source exposes this — the SEC's companyfacts API carries
        only consolidated, non-dimensional facts — so yfinance reports it as a
        capability gap and the section is simply absent without an FMP key.
        """
        ...


class ProviderBase:
    """Shared no-op defaults so a concrete provider only needs to override
    the capabilities it actually implements; everything else reports as an
    unsupported capability (empty dict) rather than raising AttributeError."""

    name: str = "base"

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_daily_bars(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        return {}

    def get_statements(self, symbol: str, years: int = 10) -> Dict[str, Any]:
        return {}

    def get_estimates(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_transcript(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_insider_trades(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_calendar(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_etf_holdings(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_revenue_segments(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_filing_sections(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_recommendation_trends(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_earnings_surprises(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_insider_sentiment(self, symbol: str, months: int = 12) -> Dict[str, Any]:
        return {}

    def get_company_news(self, symbol: str, days: int = 14) -> Dict[str, Any]:
        return {}

    def get_news_sentiment(self, symbol: str, limit: int = 50) -> Dict[str, Any]:
        return {}

    def get_peers(self, symbol: str) -> Dict[str, Any]:
        return {}

    def get_shareholder_returns(self, symbol: str) -> Dict[str, Any]:
        return {}


def is_capable(result: Optional[Dict[str, Any]]) -> bool:
    """True when a provider call produced usable data (not empty, not an
    error) — the router's signal to stop trying further providers."""
    return bool(result) and "error" not in result
