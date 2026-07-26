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

    def _try(self, chain: List[base.ProviderBase], method: str, *args: Any) -> Dict[str, Any]:
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
        return self._try(self._fundamentals_chain(), "get_insider_trades", symbol)

    def get_calendar(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._fundamentals_chain(), "get_calendar", symbol)

    def get_etf_holdings(self, symbol: str) -> Dict[str, Any]:
        return self._try(self._fundamentals_chain(), "get_etf_holdings", symbol)

    # ── introspection (Phase 2c: GET /api/providers/status) ───────────────
    def status(self) -> Dict[str, Any]:
        return {
            "fmp": {"configured": bool(settings.fmp_api_key)},
            "polygon": {"configured": bool(settings.polygon_api_key)},
            "yfinance": {"configured": True},  # always available, keyless
        }


ROUTER = ProviderRouter()
