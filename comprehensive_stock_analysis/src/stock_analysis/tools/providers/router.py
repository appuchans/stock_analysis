"""Per-capability provider fallback chains.

Every method tries providers in order and returns the first "capable" result
(:func:`base.is_capable` — non-empty, no ``error`` key), falling through to
the next provider otherwise. ``yfinance`` is always the last resort so every
capability keeps working with zero configuration; FMP/Polygon are only tried
when their API key is set, and are always tried first when available since
they cover more (FMP: 10y statements, transcripts, insider detail, real
estimate revisions; Polygon: unlimited-call quotes/bars).

Provider instances are built fresh per call from current settings rather than
cached at import time — cheap (no persistent connections beyond the shared
``tools._http.SESSION``), and lets a key added mid-process (or changed in
tests) take effect immediately without a restart.
"""

import logging
from typing import Any, Dict, List, Optional

from ...config.settings import settings
from . import base
from .yfinance_provider import YFinanceProvider

_logger = logging.getLogger(__name__)


def _fmp() -> Optional[base.ProviderBase]:
    if not settings.fmp_api_key:
        return None
    from .fmp import FMPProvider

    return FMPProvider(settings.fmp_api_key)


def _sec_api() -> Optional[base.ProviderBase]:
    if not settings.sec_api_key:
        return None
    from .sec_api import SecApiProvider

    return SecApiProvider(settings.sec_api_key)


def _finnhub() -> Optional[base.ProviderBase]:
    if not settings.finnhub_api_key:
        return None
    from .finnhub import FinnhubProvider

    return FinnhubProvider(settings.finnhub_api_key)


def _alpha_vantage_news() -> Optional[base.ProviderBase]:
    if not settings.alpha_vantage_api_key:
        return None
    from .news_sentiment import AlphaVantageNewsProvider

    return AlphaVantageNewsProvider(settings.alpha_vantage_api_key)


def _marketaux_news() -> Optional[base.ProviderBase]:
    if not settings.marketaux_api_key:
        return None
    from .news_sentiment import MarketauxNewsProvider

    return MarketauxNewsProvider(settings.marketaux_api_key)


def _polygon() -> Optional[base.ProviderBase]:
    if not settings.polygon_api_key:
        return None
    from .polygon import PolygonProvider

    return PolygonProvider(settings.polygon_api_key)


class ProviderRouter:
    def __init__(self) -> None:
        self._yfinance = YFinanceProvider()

    def _price_chain(self) -> List[base.ProviderBase]:
        polygon = _polygon()
        return ([polygon] if polygon else []) + [self._yfinance]

    def _fundamentals_chain(self) -> List[base.ProviderBase]:
        fmp = _fmp()
        return ([fmp] if fmp else []) + [self._yfinance]

    def _sentiment_chain(self) -> List[base.ProviderBase]:
        """Analyst trends, earnings surprises, insider sentiment and news.

        Finnhub leads: yfinance carries recommendation trends only patchily and
        FMP's free tier not at all, yet these are the headline inputs to the
        sentiment and fundamental stages.
        """
        finnhub = _finnhub()
        return ([finnhub] if finnhub else []) + self._fundamentals_chain()

    def _news_sentiment_chain(self) -> List[base.ProviderBase]:
        """Sentiment-scored news: Alpha Vantage, then Marketaux.

        Alpha Vantage leads on volume (50 scored articles per call against
        Marketaux's free-tier 3); Marketaux follows because it has a separate
        daily budget, so it still answers once Alpha Vantage's is spent.
        """
        return [p for p in (_alpha_vantage_news(), _marketaux_news()) if p]

    def _filings_chain(self) -> List[base.ProviderBase]:
        """Filing-derived data: sec-api.io first, then the usual fundamentals.

        sec-api.io reads the Form 4s themselves, so it leads for insider
        activity — FMP's insider endpoint is paid-tier (402 on free) and
        yfinance only carries coarse aggregates.
        """
        sec = _sec_api()
        return ([sec] if sec else []) + self._fundamentals_chain()

    def _try(
        self, chain: List[base.ProviderBase], method: str, *args: Any
    ) -> Dict[str, Any]:
        last: Dict[str, Any] = {}
        for provider in chain:
            fn = getattr(provider, method, None)
            if fn is None:
                continue
            result = fn(*args)
            if base.is_capable(result):
                return result
            last = result or last
        return last

    # ── price/market data (Polygon → yfinance) ────────────────────────────
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._price_chain(), "get_quote", symbol)

    def get_daily_bars(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        return self._try(self._price_chain(), "get_daily_bars", symbol, start, end)

    def get_batch_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Polygon-only capability (yfinance has no efficient batch quote
        call) — used by the Phase 3 rule-evaluation poller. Empty when
        Polygon isn't configured; callers must treat that as "skip this
        cycle," not an error."""
        polygon = _polygon()
        if polygon is None:
            return {}
        return polygon.get_batch_quotes(symbols)  # type: ignore[attr-defined]

    # ── fundamentals/depth (FMP → yfinance) ───────────────────────────────
    def get_statements(self, symbol: str, years: int = 10) -> Dict[str, Any]:
        return self._try(self._fundamentals_chain(), "get_statements", symbol, years)

    def get_estimates(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._fundamentals_chain(), "get_estimates", symbol)

    def get_transcript(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._fundamentals_chain(), "get_transcript", symbol)

    def get_insider_trades(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._filings_chain(), "get_insider_trades", symbol)

    def get_filing_sections(self, symbol: str) -> Dict[str, Any]:
        """Business / Risk Factors / MD&A text from the latest 10-K.

        sec-api.io only — the keyless EDGAR path in free_data_collection
        remains the fallback for callers that want scraped sections, so this
        returns {} rather than an error when no key is configured.
        """
        return self._try(self._filings_chain(), "get_filing_sections", symbol)

    def get_calendar(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._fundamentals_chain(), "get_calendar", symbol)

    def get_etf_holdings(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._fundamentals_chain(), "get_etf_holdings", symbol)

    def get_revenue_segments(self, symbol: str) -> Dict[str, Any]:
        """Revenue by product line and geography — FMP-only in practice.

        yfinance sits at the end of the chain as always, but reports this as a
        capability gap, so with no FMP key the caller simply gets {} and the
        report omits the segment section rather than failing.
        """
        return self._try(self._fundamentals_chain(), "get_revenue_segments", symbol)

    # ── analyst/news signals (Finnhub → FMP → yfinance) ───────────────────
    def get_recommendation_trends(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._sentiment_chain(), "get_recommendation_trends", symbol)

    def get_earnings_surprises(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._sentiment_chain(), "get_earnings_surprises", symbol)

    def get_insider_sentiment(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._sentiment_chain(), "get_insider_sentiment", symbol)

    def get_company_news(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._sentiment_chain(), "get_company_news", symbol)

    def get_news_sentiment(self, symbol: str) -> Dict[str, Any]:
        """News with per-ticker sentiment already scored.

        Returns {} when neither key is configured; the keyless RSS headlines in
        free_data_collection remain the fallback, so the sentiment stage still
        has material either way.
        """
        return self._try(self._news_sentiment_chain(), "get_news_sentiment", symbol)

    def get_peers(self, symbol: str) -> Dict[str, Any]:
        """Comparable companies.

        FMP leads because it returns price and market cap with each peer, which
        is what a comparables table needs; Finnhub's bare ticker list is the
        fallback and still beats the qualitative-only comparison the competitor
        stage fell back to before.
        """
        return self._try(self._fundamentals_chain() + [_f for _f in [_finnhub()] if _f],
                         "get_peers", symbol)

    def get_shareholder_returns(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._fundamentals_chain(), "get_shareholder_returns", symbol)

    # ── introspection (GET /api/providers/status) ─────────────────────────
    def status(self) -> Dict[str, Any]:
        return {
            "fmp": {"configured": bool(settings.fmp_api_key)},
            "polygon": {"configured": bool(settings.polygon_api_key)},
            "sec_api": {"configured": bool(settings.sec_api_key)},
            "finnhub": {"configured": bool(settings.finnhub_api_key)},
            "alpha_vantage": {"configured": bool(settings.alpha_vantage_api_key)},
            "marketaux": {"configured": bool(settings.marketaux_api_key)},
            "yfinance": {"configured": True},  # always available, keyless
        }


ROUTER = ProviderRouter()
