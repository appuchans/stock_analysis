"""Shared ticker-symbol validation and normalization."""

import re
from typing import Optional

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def safe_symbol(symbol: str) -> Optional[str]:
    """Return a normalized ticker symbol, or ``None`` when it is invalid."""
    if not isinstance(symbol, str):
        return None
    normalized = symbol.strip().upper()
    return normalized if _SYMBOL_RE.fullmatch(normalized) else None


def normalize_symbol(symbol: str) -> str:
    """Return a normalized ticker symbol or raise ``ValueError``."""
    normalized = safe_symbol(symbol)
    if normalized is None:
        raise ValueError("symbol must be 1-10 chars: letters, digits, '.', '-'")
    return normalized
