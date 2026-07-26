"""Restart-surviving scheduler for watchlist re-analysis and rule polling.

``schedules`` rows in SQLite are the source of truth; APScheduler is just a
stateless executor of them — on every (re)start we load enabled rows and add
a matching APScheduler job keyed by the row's id, so schedules created before
a restart keep firing without any extra bookkeeping.

Every scheduled *analysis* fire goes through ``JobManager.submit(...,
origin="scheduled")`` — the same persistent queue manual/watchlist runs use
(see jobs.py) — so the single-worker invariant (one CrewAI run at a time,
process-global token_meter/llm_budget) is never bypassed. A schedule can also
run in **monitor mode**: a data-only refresh (``StockAnalysisFlow._fetch_structured``
called directly, no ``kickoff()``, so zero LLM calls) that keeps the cached
bundle/chart fresh and lets rule evaluation see current data, without the
cost of a full analysis.

A ``daily_llm_call_cap`` (settings_kv, unset = no cap) governs scheduled-origin
jobs only — manual and watchlist-button runs are exempt, since a cap exists to
stop *unattended* spend, not to second-guess a run the user just asked for.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import db

_logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_QUOTE_POLL_JOB_ID = "_internal_quote_poll"
_QUOTE_POLL_MINUTES = 15


def _poll_price_rules() -> None:
    """Internal periodic job (not a user-visible schedule row): evaluates
    every enabled price-based rule against a fresh quote. Zero LLM calls, so
    it's safe to run even while an analysis is in progress. A no-op cycle
    (no price rules configured) costs nothing — evaluate_all_price_rules
    returns immediately without any network call."""
    try:
        from . import rules as rules_mod

        rules_mod.evaluate_all_price_rules()
    except Exception as exc:
        _logger.debug("price-rule poll skipped: %s", exc)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def validate_cron(cron_expr: str) -> None:
    """Raise ValueError if *cron_expr* isn't a valid 5-field crontab string."""
    CronTrigger.from_crontab(cron_expr)


def start() -> None:
    """Start the scheduler and load every enabled schedule. Idempotent."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.start()
    for row in db.list_schedules():
        if row["enabled"]:
            _add_job(row)
    _scheduler.add_job(
        _poll_price_rules, trigger=IntervalTrigger(minutes=_QUOTE_POLL_MINUTES),
        id=_QUOTE_POLL_JOB_ID, replace_existing=True,
    )
    _logger.info("scheduler started with %d enabled schedule(s)", len(db.list_schedules()))


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _add_job(row: Dict[str, Any]) -> None:
    if _scheduler is None:
        return
    trigger = CronTrigger.from_crontab(row["cron_expr"])
    _scheduler.add_job(
        _fire_schedule, trigger=trigger, id=row["id"], args=[row["id"]],
        replace_existing=True, misfire_grace_time=3600,
    )


def _remove_job(schedule_id: str) -> None:
    if _scheduler is not None:
        try:
            _scheduler.remove_job(schedule_id)
        except Exception:
            pass  # not currently scheduled — nothing to remove


# ── CRUD (persist + keep the live scheduler in sync) ──────────────────────────
def create_schedule(
    target: str, cron_expr: str, depth: str = "standard",
    use_cache: bool = False, monitor_only: bool = False,
) -> Dict[str, Any]:
    validate_cron(cron_expr)
    row = {
        "id": uuid.uuid4().hex, "target": target, "cron_expr": cron_expr,
        "depth": depth, "use_cache": use_cache, "monitor_only": monitor_only,
        "enabled": True, "created_at": _now_iso(),
    }
    db.add_schedule(row)
    _add_job(row)
    return row


def toggle_schedule(schedule_id: str, enabled: bool) -> bool:
    ok = db.set_schedule_enabled(schedule_id, enabled)
    if not ok:
        return False
    if enabled:
        row = db.get_schedule(schedule_id)
        if row:
            _add_job(row)
    else:
        _remove_job(schedule_id)
    return True


def remove_schedule(schedule_id: str) -> bool:
    _remove_job(schedule_id)
    return db.delete_schedule(schedule_id)


def list_schedules() -> List[Dict[str, Any]]:
    return db.list_schedules()


# ── firing ─────────────────────────────────────────────────────────────────────
def _target_symbols(target: str) -> List[str]:
    if target == "watchlist":
        return [row["symbol"] for row in db.list_symbols()]
    return [target]


def _daily_cap() -> Optional[int]:
    raw = db.get_setting("daily_llm_call_cap")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def refresh_data_only(symbol: str, use_cache: bool = False) -> bool:
    """Refresh a symbol's structured data bundle / chart JSON with zero LLM
    calls — ``StockAnalysisFlow._fetch_structured`` does the real fetch;
    ``kickoff()`` (and every agent/crew it would run) is never invoked."""
    from ..crew.flow_crew import StockAnalysisFlow
    from ..tools.free_data_collection import resolve_symbol

    info = resolve_symbol(symbol)
    if info is None:
        _logger.warning("monitor refresh skipped for invalid symbol %s", symbol)
        return False
    asset_type = info["asset_type"]
    flow = StockAnalysisFlow(use_data_cache=use_cache, asset_type=asset_type)
    flow.state.symbol = symbol
    flow.state.asset_type = asset_type  # already resolved above — skip a redundant detect call
    flow.state.analysis_depth = "standard"
    try:
        flow._fetch_structured()
        return True
    except Exception as exc:
        _logger.warning("monitor refresh failed for %s: %s", symbol, exc)
        return False


def _fire_schedule(schedule_id: str) -> None:
    row = db.get_schedule(schedule_id)
    if row is None or not row["enabled"]:
        return
    symbols = _target_symbols(row["target"])
    if not symbols:
        db.record_schedule_run(schedule_id, "skipped: no symbols")
        return

    if row["monitor_only"]:
        results = [refresh_data_only(sym, bool(row["use_cache"])) for sym in symbols]
        ok = sum(1 for r in results if r)
        db.record_schedule_run(schedule_id, f"monitor refresh: {ok}/{len(symbols)} ok")
        _evaluate_rules_after_refresh(symbols)
        return

    cap = _daily_cap()
    if cap is not None and db.scheduled_llm_calls_today() >= cap:
        db.record_schedule_run(schedule_id, "skipped: daily LLM call cap reached")
        _logger.info("schedule %s skipped — daily cap reached", schedule_id)
        return

    from .jobs import manager

    queued = []
    for sym in symbols:
        job = manager.submit(sym, row["depth"], "auto", bool(row["use_cache"]), origin="scheduled")
        queued.append(job.symbol)
    db.record_schedule_run(schedule_id, f"queued: {', '.join(queued)}")


def _evaluate_rules_after_refresh(symbols: List[str]) -> None:
    """Evaluate price rules immediately after a monitor-mode data refresh, in
    addition to the periodic quote-poll job — best-effort, never lets a rule
    error interrupt the schedule firing."""
    from . import rules as rules_mod

    for sym in symbols:
        try:
            rules_mod.evaluate_price_rules_for_symbol(sym)
        except Exception as exc:
            _logger.debug("rule evaluation skipped for %s: %s", sym, exc)
