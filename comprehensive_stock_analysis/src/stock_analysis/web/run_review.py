"""Post-run artifact review: did this run actually produce what the UI needs?

A run can report ``completed`` and still be missing pieces the interface
depends on. The flow deliberately degrades rather than aborts — a failed
recommendation crew is caught and logged, and the HTML report is rendered
regardless — so a partial run looks successful from the outside.

That failure mode was real: an OpenAI structured-output rejection made
``synthesize_recommendation`` fail on *every* run, so no
``<SYM>_investment_recommendation.json`` was written and history tiles silently
lost their rating badge, target price and accent border. Nothing surfaced it;
it was noticed by eye, weeks later, by comparing two tiles.

The checks below are written against the **display contract** — the exact keys
``reports_index.list_reports()`` and ``dashboard.js`` read — so "the review
passed" means "the UI has what it needs", not merely "some files exist".

This never raises and never changes a run's outcome. It reports.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import _paths

_logger = logging.getLogger(__name__)

# Below this a "report" is a stub/error page rather than a real render.
_MIN_HTML_BYTES = 2048

_VALID_RECOMMENDATIONS = {
    "STRONG_BUY",
    "BUY",
    "HOLD",
    "SELL",
    "STRONG_SELL",
}


def _issue(severity: str, code: str, detail: str) -> Dict[str, str]:
    return {"severity": severity, "code": code, "detail": detail}


def _read_json(path) -> Optional[Dict[str, Any]]:
    """None = unreadable/missing (caller distinguishes); {} is a valid parse."""
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return None


def _is_number(v: Any) -> bool:
    """Numeric *as the UI sees it* — mirrors reports_index._num(), which coerces
    with float().

    Deliberately tolerant of numeric strings: older recommendation files stored
    Decimal-typed prices as JSON strings ("58"), and the gallery renders those
    correctly. Flagging them would be crying wolf. What this must still catch is
    the case the price validator exists to absorb — an LLM returning
    "115 (percentage-based target)" — which no amount of coercion will rescue.
    """
    if isinstance(v, bool):
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f  # reject NaN, as _num() does


def _check_html(symbol: str, issues: List[Dict[str, str]]) -> None:
    path = _paths.html_path(symbol)
    if path is None or not path.exists():
        issues.append(
            _issue("error", "html_missing", "no HTML report — the card won't open")
        )
        return
    try:
        size = path.stat().st_size
    except OSError as exc:
        issues.append(_issue("error", "html_unreadable", f"cannot stat report: {exc}"))
        return
    if size < _MIN_HTML_BYTES:
        issues.append(
            _issue(
                "warning",
                "html_too_small",
                f"report is only {size}B — likely a stub rather than a real render",
            )
        )


def _check_chart_data(symbol: str, issues: List[Dict[str, str]]) -> None:
    """chart_data.json drives the tile header, the stat rows and the sparkline,
    and is the whole source for the interactive Overview."""
    chart = _read_json(_paths.chart_path(symbol))
    if chart is None:
        issues.append(
            _issue(
                "error",
                "chart_data_missing",
                "no chart_data.json — tile shows no name, stats or sparkline",
            )
        )
        return

    if not (chart.get("company") or {}).get("name"):
        issues.append(
            _issue("warning", "company_name_missing", "tile will show only the ticker")
        )
    if not chart.get("asset_type"):
        issues.append(
            _issue(
                "warning",
                "asset_type_missing",
                "asset_type absent — ETF vs stock tile layout can't be chosen",
            )
        )

    stats = chart.get("key_stats") or {}
    if not _is_number(stats.get("current_price")):
        issues.append(
            _issue(
                "error",
                "current_price_invalid",
                f"key_stats.current_price is {stats.get('current_price')!r}, "
                "not a number",
            )
        )

    history = chart.get("price_history") or []
    if not history:
        issues.append(
            _issue("warning", "price_history_empty", "tile sparkline will be blank")
        )
    elif not any(_is_number(p.get("close")) for p in history if isinstance(p, dict)):
        issues.append(
            _issue(
                "warning",
                "price_history_unusable",
                "price_history has no numeric closes — sparkline will be blank",
            )
        )


def _check_recommendation(
    symbol: str, asset_type: Optional[str], issues: List[Dict[str, str]]
) -> None:
    """The rating badge, accent border and target/upside rows all come from
    here. Its absence is exactly the regression this module was written for."""
    rec = _read_json(_paths.recommendation_path(symbol))
    if rec is None:
        issues.append(
            _issue(
                "error",
                "recommendation_missing",
                "no investment_recommendation.json — tile loses its rating badge, "
                "target price and accent border (check whether the recommendation "
                "crew failed)",
            )
        )
        return

    value = rec.get("recommendation")
    if not value:
        issues.append(
            _issue("error", "recommendation_empty", "recommendation field is empty")
        )
    elif str(value).upper().replace(" ", "_") not in _VALID_RECOMMENDATIONS:
        issues.append(
            _issue(
                "warning",
                "recommendation_unrecognised",
                f"recommendation {value!r} is outside the known set — the badge "
                "may render unstyled",
            )
        )

    confidence = rec.get("confidence")
    if not _is_number(confidence):
        issues.append(
            _issue("warning", "confidence_invalid", f"confidence is {confidence!r}")
        )
    elif not 0 <= float(confidence) <= 1:
        issues.append(
            _issue(
                "warning",
                "confidence_out_of_range",
                f"confidence {confidence} is outside 0–1",
            )
        )

    if not rec.get("risk_level"):
        issues.append(_issue("warning", "risk_level_missing", "risk_level is empty"))

    # target_price may legitimately be absent (the advisor can decline to set
    # one), but a *present* value must be numeric or the tile's upside maths
    # silently breaks.
    target = rec.get("target_price")
    if target is not None and not _is_number(target):
        issues.append(
            _issue(
                "error",
                "target_price_not_numeric",
                f"target_price is {target!r}, not a number — upside can't be computed",
            )
        )
    stop = rec.get("stop_loss")
    if stop is not None and not _is_number(stop):
        issues.append(
            _issue("warning", "stop_loss_not_numeric", f"stop_loss is {stop!r}")
        )


def review_run(symbol: str, degradations: Optional[List[str]] = None) -> Dict[str, Any]:
    """Check a completed run against what the UI needs to display it.

    ``degradations`` is the flow's own list of caught-and-worked-around
    failures. They are folded in because the two views are complementary: the
    artifact checks see *what is missing now* (including from an earlier run),
    while degradations explain *what went wrong this time* — a stage can fail
    and still leave a stale file from a previous run sitting on disk, which
    would otherwise read as healthy.

    Returns ``{"ok", "issues", "error_count", "warning_count", "reviewed_at"}``.
    ``ok`` is False only for ``error`` severity — warnings mean degraded but
    displayable.
    """
    issues: List[Dict[str, str]] = []
    try:
        _check_html(symbol, issues)
        _check_chart_data(symbol, issues)
        chart = _read_json(_paths.chart_path(symbol)) or {}
        _check_recommendation(symbol, chart.get("asset_type"), issues)
        for detail in degradations or []:
            issues.append(_issue("warning", "stage_degraded", detail))
    except Exception as exc:  # pragma: no cover - review must never break a run
        _logger.exception("run review crashed for %s", symbol)
        issues.append(_issue("warning", "review_failed", str(exc)))

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    return {
        "ok": not errors,
        "issues": issues,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
    }


def review_and_log(
    symbol: str, degradations: Optional[List[str]] = None
) -> Dict[str, Any]:
    """review_run() plus a log line per issue, so a degraded run is visible in
    the log without anyone thinking to look at the UI."""
    result = review_run(symbol, degradations=degradations)
    for issue in result["issues"]:
        log = _logger.error if issue["severity"] == "error" else _logger.warning
        log(
            "[run-review] %s: %s — %s",
            symbol,
            issue["code"],
            issue["detail"],
        )
    if result["ok"] and not result["issues"]:
        _logger.info("[run-review] %s: all display data present", symbol)
    elif result["ok"]:
        _logger.info(
            "[run-review] %s: displayable with %d warning(s)",
            symbol,
            result["warning_count"],
        )
    else:
        _logger.error(
            "[run-review] %s: %d error(s), %d warning(s) — the UI will render "
            "this run incompletely",
            symbol,
            result["error_count"],
            result["warning_count"],
        )
    return result
