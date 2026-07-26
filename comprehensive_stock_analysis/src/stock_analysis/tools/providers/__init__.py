"""Pluggable market-data providers behind a single router.

``router.ROUTER`` is the entry point every caller should use: it tries a
per-capability provider chain (premium provider first when its API key is
configured, always falling back to the keyless ``yfinance`` provider) so the
app is fully functional with zero configuration and gets richer data the
moment a key is added to ``.env``.
"""

from .router import ROUTER

__all__ = ["ROUTER"]
