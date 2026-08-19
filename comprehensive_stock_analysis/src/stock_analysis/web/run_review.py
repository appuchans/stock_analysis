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
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config.settings import settings
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


def _check_target_against_model(
    symbol: str, rec: Dict[str, Any], issues: List[Dict[str, str]]
) -> None:
    """The published target must be reconcilable with the run's own DCF.

    A reviewer rejected a report whose base case was $415 and bull case $539
    beside a published $565 target and a $495 traded price — the valuation
    exhibit contradicted the rating on the same page. Warning rather than
    error: a target outside the modelled range is legitimate when the memo
    names the assumption that bridges it (normalising capex, a re-rating), so
    this flags for a human read instead of blocking display.
    """
    chart = _read_json(_paths.chart_path(symbol)) or {}
    scenarios = chart.get("valuation_scenarios") or []
    values = [
        float(s["intrinsic_per_share"])
        for s in scenarios
        if isinstance(s, dict) and _is_number(s.get("intrinsic_per_share"))
    ]
    if not values:
        return

    lo, hi = min(values), max(values)
    target = rec.get("target_price")
    if _is_number(target) and not lo <= float(target) <= hi:
        issues.append(
            _issue(
                "warning",
                "target_outside_valuation_range",
                f"target {float(target):.2f} sits outside the DCF range "
                f"{lo:.2f}–{hi:.2f} — the memo must name the assumption that "
                "bridges the gap, or the target should move inside it",
            )
        )

    price = (chart.get("key_stats") or {}).get("current_price")
    rating = str(rec.get("recommendation") or "").upper()
    if _is_number(price) and hi < float(price) and "BUY" in rating:
        issues.append(
            _issue(
                "warning",
                "valuation_contradicts_rating",
                f"every DCF scenario (max {hi:.2f}) is below the traded price "
                f"{float(price):.2f} while the rating is {rating} — the "
                "valuation exhibit argues against the call",
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

    _check_target_against_model(symbol, rec, issues)

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


# Text that only ever appears when the model echoed its own instructions back
# instead of following them. Real leaks seen in output: "The core reason is
# plain English: Microsoft owns…" (from "the core reason in plain English"),
# and unreplaced {placeholders} when interpolation silently failed.
_LEAK_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (
        "instruction_echoed",
        re.compile(
            r"\b(?:the\s+)?core\s+reason\s+is\s+plain\s+English\b"
            r"|\bassume\s+the\s+reader\s+has\s+never\s+heard\s+of\s+it\b"
            r"|\bin\s+plain,?\s+direct\s+prose\b"
            r"|\bstated\s+as\s+business\s+risks\s+not\s+beta\s+values\b"
            r"|\btwo\s+plain-English\s+sentences\b"
            r"|\bYour\s+memo\s+must\s+follow\b"
            r"|\bheading\s+lines\s+contain\s+ONLY\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_scaffold_leaked",
        re.compile(r"RIGOR REQUIREMENTS|expected_output|analyses_summary"),
    ),
    (
        # The reader is told about the machinery that produced the report:
        # "the data package provided in the prompt", "I cannot cite ...".
        # These come from asking for citations while banning tool names, and
        # they read as an auto-generated dump rather than a research note.
        "pipeline_narrated",
        re.compile(
            r"\b(?:I\s+)?cannot\s+cite\b"
            r"|\bdata\s+package\b"
            r"|\bprovided\s+in\s+the\s+prompt\b"
            r"|\bcollected\s+data\s+package\b"
            r"|\bsource\s+material\b",
            re.IGNORECASE,
        ),
    ),
    (
        # Emitted whenever rec_history is empty *or* the lookup raised, so a
        # plain CLI run says it every time. It is internal bookkeeping.
        "run_bookkeeping_leaked",
        re.compile(
            r"first\s+recorded\s+recommendation"
            r"|no\s+prior\s+analysis\s+on\s+record",
            re.IGNORECASE,
        ),
    ),
    (
        "placeholder_uninterpolated",
        # A real interpolation failure — the reader would see literal
        # {financials_data} in the report.
        re.compile(
            r"\{(?:symbol|analyst|financials|ownership|sentiment|technical|"
            r"collected|segments|peers|earnings_surprises|filing_sections|"
            r"shareholder_returns|statements_10y|transcript)[a-z_]*\}"
        ),
    ),
]

# Files a reader actually sees. The run report is operator output and is
# allowed to quote whatever it likes.
_READER_FACING_SUFFIXES = (
    "_analysis.md",
    "_comprehensive_report.md",
    "_investment_recommendation.json",
)


_SHORT_INTEREST_RE = re.compile(
    r"([\d.]+)\s*%\s*of\s+(?:the\s+)?(?:float|shares outstanding)", re.IGNORECASE
)
_ANALYST_COUNT_RE = re.compile(r"(\d{1,3})\s+analysts\b", re.IGNORECASE)


def _check_narrative_consistency(symbol: str, issues: List[Dict[str, str]]) -> None:
    """Do the narrative's figures still match the data they came from?

    The synthesis stage rewrites nine specialist reports into one document, and
    it can silently corrupt a number on the way through. On an IBM run every
    upstream workpaper said short interest was 2.62% of float and the collected
    data agreed — the client-facing narrative said 2.1%. Nothing caught it:
    the artifacts all existed, all validated, and the figure was simply wrong.

    Only figures with an unambiguous structured counterpart are checked, so a
    warning here means a real contradiction rather than a parsing guess.
    """
    chart = _read_json(_paths.chart_path(symbol)) or {}
    path = Path(settings.report_output_dir) / symbol.upper()
    narrative_path = path / f"{symbol.upper()}_comprehensive_report.md"
    try:
        text = narrative_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    from ..tools.report_tools import _split_gaps

    text = _split_gaps(text)[0]

    truth = (chart.get("sentiment_snapshot") or {}).get("short_pct_of_float")
    if _is_number(truth):
        claimed = [float(m) for m in _SHORT_INTEREST_RE.findall(text)]
        # Rounding to one decimal is fine; a different number is not.
        if claimed and not any(abs(c - float(truth)) <= 0.06 for c in claimed):
            issues.append(
                _issue(
                    "warning",
                    "narrative_contradicts_data",
                    f"narrative says short interest is "
                    f"{', '.join(f'{c}%' for c in claimed)} of float, but the "
                    f"collected data says {float(truth)}%",
                )
            )

    counts = (chart.get("analyst") or {}).get("rating_counts") or {}
    total = counts.get("total_analysts")
    if not _is_number(total):
        parts = [
            counts.get(k)
            for k in ("strong_buy", "buy", "hold", "sell", "strong_sell")
            if _is_number(counts.get(k))
        ]
        total = sum(float(p) for p in parts) if parts else None
    if _is_number(total):
        claimed_counts = [int(m) for m in _ANALYST_COUNT_RE.findall(text)]
        if claimed_counts and int(float(total)) not in claimed_counts:
            issues.append(
                _issue(
                    "warning",
                    "narrative_contradicts_data",
                    f"narrative cites {claimed_counts} analysts, but the "
                    f"consensus data covers {int(float(total))}",
                )
            )


def _check_prompt_leaks(symbol: str, issues: List[Dict[str, str]]) -> None:
    """Flag instruction text that leaked into reader-facing output.

    A model that restates its brief ("the core reason is plain English:")
    produces prose that is subtly wrong in a way no other check catches — the
    artifacts all exist and validate, the sentence is simply not English. It
    has to be caught by inspection after generation, which is what this is.
    """
    report_dir = Path(settings.report_output_dir) / symbol.upper()
    if not report_dir.is_dir():
        return
    for path in sorted(report_dir.iterdir()):
        if not path.is_file() or not path.name.endswith(_READER_FACING_SUFFIXES):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # The "Data Sources & Gaps" footer is operator-facing — the renderer
        # strips it into the run report before the reader sees anything. Scan
        # only what actually ships, or every stage file trips the pipeline
        # patterns on prose no client ever reads.
        if path.name.endswith(".md"):
            from ..tools.report_tools import _split_gaps

            text = _split_gaps(text)[0]
        for code, pattern in _LEAK_PATTERNS:
            match = pattern.search(text)
            if match:
                issues.append(
                    _issue(
                        # Warning, not error: the report still displays. This
                        # module's contract is that `ok` is False only when the
                        # UI cannot show the run — leaked prose is ugly, not
                        # fatal. Blocking publication is the abort gate's job.
                        "warning",
                        code,
                        f"{path.name}: prompt text reached the report "
                        f"— {match.group(0)[:60]!r}",
                    )
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
        _check_prompt_leaks(symbol, issues)
        _check_narrative_consistency(symbol, issues)
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
