"""Builds the history gallery by scanning the reports directory on disk."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import _paths

_logger = logging.getLogger(__name__)


def _read_json(path) -> Dict[str, Any]:
    try:
        if path and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.debug("history: could not read %s: %s", path, exc)
    return {}


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f  # drop NaN
    except (TypeError, ValueError):
        return None


def list_reports() -> List[Dict[str, Any]]:
    """One entry per symbol with an HTML report, newest first.

    Best-effort: a symbol is included only if its HTML report exists; chart and
    recommendation data are merged when present but never required.
    """
    root = _paths.reports_root()
    items: List[Dict[str, Any]] = []
    if not root.exists():
        return items

    for child in root.iterdir():
        if not child.is_dir():
            continue
        sym = _paths.safe_symbol(child.name)
        if not sym:
            continue
        html = _paths.html_path(sym)
        if not html or not html.exists():
            continue  # require a viewable report

        chart = _read_json(_paths.chart_path(sym))
        rec = _read_json(_paths.recommendation_path(sym))
        company = chart.get("company") or {}
        stats = chart.get("key_stats") or {}

        items.append({
            "symbol": sym,
            "name": company.get("name"),
            "sector": company.get("sector"),
            "recommendation": rec.get("recommendation"),
            "target_price": _num(rec.get("target_price")),
            "confidence": rec.get("confidence"),
            "risk_level": rec.get("risk_level"),
            "current_price": _num(stats.get("current_price")),
            "market_cap": _num(stats.get("market_cap")),
            "pe_ratio": _num(stats.get("pe_ratio")),
            "high_52w": _num(stats.get("high_52w")),
            "low_52w": _num(stats.get("low_52w")),
            "has_html": True,
            "has_chart": bool(chart),
            "mtime": datetime.fromtimestamp(html.stat().st_mtime).isoformat(timespec="seconds"),
        })

    items.sort(key=lambda it: it.get("mtime") or "", reverse=True)
    return items
