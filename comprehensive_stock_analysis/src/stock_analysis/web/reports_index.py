"""Builds the history gallery by scanning the reports directory on disk.

Each run writes a small ``<SYM>_run_status.json`` marker (completed / aborted /
failed) so the gallery can show the outcome even when a run produced no report.
"""

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


def _analyzed_at(sym: str, status_data: Dict[str, Any]) -> Optional[str]:
    """Best estimate of when the analysis actually ran, as an ISO string.

    Prefers the run-status marker, then the newest *data* artifact mtime. The
    HTML report is deliberately excluded — re-rendering it (e.g. a template
    change) bumps its mtime and would otherwise reorder old analyses to the top.
    """
    if status_data.get("finished_at"):
        return status_data["finished_at"]
    d = _paths.report_dir(sym)
    mtimes = []
    candidates = [_paths.chart_path(sym), _paths.recommendation_path(sym)]
    if d:
        candidates.append(d / f"{sym}_data.json")
        candidates.append(d / f"{sym}_comprehensive_report.md")
    for p in candidates:
        try:
            if p and p.exists():
                mtimes.append(p.stat().st_mtime)
        except OSError:
            pass
    if not mtimes:
        html = _paths.html_path(sym)  # last resort
        try:
            if html and html.exists():
                mtimes.append(html.stat().st_mtime)
        except OSError:
            pass
    return (
        datetime.fromtimestamp(max(mtimes)).isoformat(timespec="seconds")
        if mtimes else None
    )


def write_run_status(symbol: str, status: str) -> None:
    """Persist the latest run outcome for a symbol (best-effort)."""
    path = _paths.status_path(symbol)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"status": status, "finished_at": datetime.now().isoformat(timespec="seconds")}),
            encoding="utf-8",
        )
    except OSError as exc:
        _logger.debug("could not write run status for %s: %s", symbol, exc)


def backfill_rec_history() -> int:
    """One-time capture of pre-existing recommendation snapshots into
    rec_history, for reports that were generated before that table existed
    (or by the CLI, which never went through the web job path). Best-effort
    and idempotent — ``db.record_recommendation`` de-dupes on (symbol,
    recorded_at), and file mtime stands in for a real timestamp since these
    older snapshots never recorded one.

    Called once at web app startup; cheap on repeat runs since every row it
    would insert already exists after the first pass.
    """
    from . import db

    root = _paths.reports_root()
    if not root.exists():
        return 0

    inserted = 0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        sym = _paths.safe_symbol(child.name)
        if not sym:
            continue
        chart = _read_json(_paths.chart_path(sym))
        price = ((chart.get("key_stats") or {}).get("current_price"))
        for path in (_paths.prev_recommendation_path(sym), _paths.recommendation_path(sym)):
            if path is None or not path.exists():
                continue
            rec = _read_json(path)
            if not rec:
                continue
            try:
                mtime = path.stat().st_mtime
                recorded_at = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
            except OSError:
                continue
            # Only the current (non-_prev) snapshot's price is known; an older
            # _prev snapshot's contemporaneous price was never captured.
            is_current = path.name.endswith("_investment_recommendation.json")
            db.record_recommendation(
                symbol=sym,
                recorded_at=recorded_at,
                recommendation=rec.get("recommendation"),
                target_price=_num(rec.get("target_price")),
                stop_loss=_num(rec.get("stop_loss")),
                confidence=_num(rec.get("confidence")),
                price_at_rec=_num(price) if is_current else None,
            )
            inserted += 1
    return inserted


def list_reports() -> List[Dict[str, Any]]:
    """One entry per symbol that has a report or a run-status marker, newest first.

    A completed run has a viewable HTML report; aborted/failed runs may have no
    report but still appear with their status so the user sees what happened.
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
        has_html = bool(html and html.exists())
        status_data = _read_json(_paths.status_path(sym))
        status = status_data.get("status")
        # Show a symbol only if it has a viewable report, or a non-completed
        # outcome worth surfacing (aborted/failed/incomplete). A bare "completed"
        # marker with no report is anomalous and skipped.
        if not has_html and status in (None, "completed"):
            continue

        chart = _read_json(_paths.chart_path(sym))
        rec = _read_json(_paths.recommendation_path(sym))
        company = chart.get("company") or {}
        stats = chart.get("key_stats") or {}
        etf = chart.get("etf_profile") or {}
        # Compact price series for the card sparkline (last ~30 weekly closes).
        spark = [p.get("close") for p in (chart.get("price_history") or [])][-30:]
        # Default a marker-less report (e.g. produced by the CLI) to completed.
        effective_status = status or ("completed" if has_html else "incomplete")
        mtime = _analyzed_at(sym, status_data)

        items.append({
            "symbol": sym,
            "name": company.get("name"),
            "sector": company.get("sector"),
            "status": effective_status,
            "asset_type": chart.get("asset_type"),
            "recommendation": rec.get("recommendation"),
            "target_price": _num(rec.get("target_price")),
            "confidence": rec.get("confidence"),
            "risk_level": rec.get("risk_level"),
            "current_price": _num(stats.get("current_price")),
            "market_cap": _num(stats.get("market_cap")),
            "pe_ratio": _num(stats.get("pe_ratio")),
            "high_52w": _num(stats.get("high_52w")),
            "low_52w": _num(stats.get("low_52w")),
            # ETF-relevant fund facts (None for stocks) for the history card.
            "aum_bn": _num(etf.get("total_assets_bn")),
            "expense_ratio": _num(etf.get("expense_ratio")),
            "distribution_yield": _num(etf.get("distribution_yield")),
            "ytd_return": _num(etf.get("ytd_return")),
            "has_html": has_html,
            "has_chart": bool(chart),
            "spark": spark,
            "mtime": mtime,
        })

    items.sort(key=lambda it: it.get("mtime") or "", reverse=True)
    return items
