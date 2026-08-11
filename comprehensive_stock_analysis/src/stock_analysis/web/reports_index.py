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


def _ytd_return(price_history: Any) -> Optional[float]:
    """Year-to-date return as a fraction (0.12 = +12%), from the price history.

    Stocks have no ytd_return in key_stats the way an ETF profile does, so it is
    derived here rather than adding a fetch. The reference year comes from the
    *last data point*, not today's date, so the number stays consistent with the
    series being charted even if the report is a few days stale.

    Baseline is the final close of the previous year when the series reaches
    back that far (the conventional YTD basis), otherwise the first close of the
    current year — which understates YTD slightly, but only for symbols with
    under a year of history.
    """
    if not isinstance(price_history, list) or len(price_history) < 2:
        return None
    points = []
    for p in price_history:
        if not isinstance(p, dict):
            continue
        close = _num(p.get("close"))
        date = p.get("date")
        if close is None or not close or not isinstance(date, str) or len(date) < 4:
            continue
        try:
            year = int(date[:4])
        except ValueError:
            continue
        points.append((date, year, close))
    if len(points) < 2:
        return None
    points.sort(key=lambda t: t[0])

    last_date, last_year, last_close = points[-1]
    prior = [p for p in points if p[1] < last_year]
    if prior:
        baseline = prior[-1][2]
    else:
        current = [p for p in points if p[1] == last_year]
        if len(current) < 2:
            return None
        baseline = current[0][2]
    if not baseline:
        return None
    return (last_close / baseline) - 1.0


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
        if mtimes
        else None
    )


def write_run_status(
    symbol: str, status: str, review: Optional[Dict[str, Any]] = None
) -> None:
    """Persist the latest run outcome for a symbol (best-effort).

    ``review`` is the post-run display-contract verdict (see run_review.py). It
    lives in the marker so the gallery can flag an incomplete run without
    re-deriving it, and so the verdict survives a restart.
    """
    path = _paths.status_path(symbol)
    if path is None:
        return
    payload: Dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    if review is not None:
        payload["review"] = review
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
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
        price = (chart.get("key_stats") or {}).get("current_price")
        for path in (
            _paths.prev_recommendation_path(sym),
            _paths.recommendation_path(sym),
        ):
            if path is None or not path.exists():
                continue
            rec = _read_json(path)
            if not rec:
                continue
            try:
                mtime = path.stat().st_mtime
                recorded_at = datetime.fromtimestamp(mtime).isoformat(
                    timespec="seconds"
                )
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

        items.append(
            {
                "symbol": sym,
                "name": company.get("name"),
                "sector": company.get("sector"),
                "status": effective_status,
                # Post-run display-contract verdict, so a run that completed but
                # is missing pieces the tile needs can be flagged rather than
                # quietly rendering half a card.
                "review": status_data.get("review"),
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
                "beta": _num(stats.get("beta")),
                "dividend_yield": _num(stats.get("dividend_yield")),
                # ETF-relevant fund facts (None for stocks) for the history card.
                "aum_bn": _num(etf.get("total_assets_bn")),
                "expense_ratio": _num(etf.get("expense_ratio")),
                "distribution_yield": _num(etf.get("distribution_yield")),
                # The ETF profile publishes its own YTD; stocks have none, so
                # fall back to deriving it from the charted series.
                "ytd_return": (
                    _num(etf.get("ytd_return"))
                    if etf.get("ytd_return") is not None
                    else _ytd_return(chart.get("price_history"))
                ),
                "has_html": has_html,
                "has_chart": bool(chart),
                "spark": spark,
                "mtime": mtime,
            }
        )

    items.sort(key=lambda it: it.get("mtime") or "", reverse=True)
    return items
