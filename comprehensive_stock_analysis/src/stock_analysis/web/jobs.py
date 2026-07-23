"""Single-worker job queue for serialized analysis runs.

Runs MUST be serialized: ``token_meter`` and ``llm_budget`` are process-global
and reset at the start of each run, so two concurrent in-process analyses would
corrupt each other's accounting. A ``ThreadPoolExecutor(max_workers=1)`` is the
serialization point — exactly one ``_run`` executes at a time.

Unlike the earlier design, a second submission while one is active is **queued**,
not rejected: ``submit`` appends to a FIFO the single worker drains in order.
Jobs are mirrored into SQLite (best-effort) so the queue and its history survive
a restart — ``recover`` re-enqueues anything left queued and flags runs that were
interrupted mid-flight.

The blocking analysis runs in the worker thread — never in the request handler —
so the event loop stays responsive and the status endpoint can be polled live.
"""

from __future__ import annotations  # the `progress` field must not shadow the module

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import progress

_logger = logging.getLogger(__name__)

_ACTIVE_STATES = ("queued", "running")
_DEPTH_RANK = {"quick": 0, "standard": 1, "deep": 2}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class JobConflictError(RuntimeError):
    """Retained for backward compatibility; no longer raised (runs now queue)."""


@dataclass
class Job:
    id: str
    symbol: str
    depth: str
    asset_type: str
    use_cache: bool
    origin: str = "manual"
    state: str = "queued"
    stage: Optional[str] = None
    progress: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)
    llm_calls: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    company_name: Optional[str] = None
    cancel_requested: bool = False
    created_at: str = field(default_factory=_now)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    tracker: Optional[progress.StageTracker] = None


class JobManager:
    """Owns the single worker and the job registry (single-user)."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
        self._jobs: Dict[str, Job] = {}
        self._pending: List[str] = []  # queued job ids, FIFO (for position + resume)
        self._active_id: Optional[str] = None
        self._lock = threading.Lock()
        self._recovered = False

    # ── persistence (best-effort — the in-memory queue is authoritative) ──────
    def _persist(self, job: Job) -> None:
        try:
            from . import db

            db.upsert_job({
                "id": job.id,
                "symbol": job.symbol,
                "depth": job.depth,
                "asset_type": job.asset_type,
                "use_cache": 1 if job.use_cache else 0,
                "origin": job.origin,
                "state": job.state,
                "stage": job.stage,
                "error": job.error,
                "company_name": job.company_name,
                "progress": float(job.progress),
                "llm_calls": int(job.llm_calls),
                "total_tokens": int((job.token_usage or {}).get("total_tokens") or 0),
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
            })
        except Exception:  # persistence must never break a run
            pass

    # ── submission ──────────────────────────────────────────────────────────
    def submit(
        self,
        symbol: str,
        depth: str,
        asset_type: str,
        use_cache: bool,
        origin: str = "manual",
    ) -> Job:
        """Enqueue an analysis. If an equal-or-deeper run for the same symbol is
        already queued/running, return that job instead (coalescing) so repeated
        or scheduled submissions never pile up duplicate work."""
        with self._lock:
            existing = self._find_coalescible(symbol, depth)
            if existing is not None:
                return existing
            job = Job(
                id=uuid.uuid4().hex,
                symbol=symbol,
                depth=depth,
                asset_type=asset_type,
                use_cache=use_cache,
                origin=origin,
            )
            self._jobs[job.id] = job
            self._pending.append(job.id)
        self._persist(job)
        self._executor.submit(self._run_wrapper, job.id)
        return job

    def _find_coalescible(self, symbol: str, depth: str) -> Optional[Job]:
        """A queued/running job for *symbol* whose depth covers *depth* (caller
        must hold the lock)."""
        want = _DEPTH_RANK.get(depth, 1)
        for jid in self._pending + ([self._active_id] if self._active_id else []):
            job = self._jobs.get(jid)
            if (
                job is not None
                and job.symbol == symbol
                and job.state in _ACTIVE_STATES
                and _DEPTH_RANK.get(job.depth, 1) >= want
            ):
                return job
        return None

    def _queue_position(self, job: Job) -> int:
        """0 = running/next up; N = N jobs ahead in the queue."""
        with self._lock:
            if job.id == self._active_id or job.state == "running":
                return 0
            try:
                return self._pending.index(job.id) + (0 if self._active_id is None else 1)
            except ValueError:
                return 0

    # ── cancellation ─────────────────────────────────────────────────────────
    def cancel(self, job_id: str):
        """Request cancellation. Returns None (unknown), False (not active), or
        True (requested). A still-queued job is cancelled immediately."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.state not in _ACTIVE_STATES:
                return False
            job.cancel_requested = True
            if job.state == "queued":
                # Never started — drop it from the queue without touching the
                # running job's budget.
                if job_id in self._pending:
                    self._pending.remove(job_id)
                job.state = "aborted"
                job.stage = "Aborted"
                job.finished_at = _now()
                self._persist(job)
                _logger.info("queued job %s (%s) cancelled before start", job_id, job.symbol)
                return True
        from ..llm_budget import request_abort

        request_abort()
        _logger.info("cancellation requested for running job %s (%s)", job_id, job.symbol)
        return True

    # ── worker (runs in the single worker thread) ────────────────────────────
    def _run_wrapper(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        with self._lock:
            if job_id in self._pending:
                self._pending.remove(job_id)
            # A job cancelled while queued is already terminal — skip it.
            if job.state != "queued":
                return
            self._active_id = job_id
        try:
            self._run(job)
        finally:
            with self._lock:
                if self._active_id == job_id:
                    self._active_id = None

    def _run(self, job: Job) -> None:
        # analyze_stock() never lets AnalysisAbortedError propagate — it catches
        # everything internally and returns a {"status": "failed", ...} dict, so
        # abort-detection here happens via result.get("status") below, not a
        # try/except around AnalysisAbortedError.
        from ..main import StockAnalysisApp

        job.state = "running"
        job.started_at = _now()
        job.tracker = progress.StageTracker()
        progress.set_active(job.tracker)
        self._persist(job)
        try:
            from ..tools.free_data_collection import resolve_symbol

            info = resolve_symbol(job.symbol)
            if info is None:
                job.state = "failed"
                job.stage = "Failed"
                job.error = f"'{job.symbol}' doesn't look like a valid stock or ETF symbol"
                return
            job.company_name = info["name"]
            # Archive the previous recommendation so diff can compare before/after
            try:
                import shutil

                from . import _paths as _p

                cur = _p.recommendation_path(job.symbol)
                prev = _p.prev_recommendation_path(job.symbol)
                if cur and prev and cur.exists():
                    shutil.copy2(cur, prev)
            except Exception:
                pass
            app = StockAnalysisApp(
                depth=job.depth,
                asset_type=job.asset_type,
                use_data_cache=job.use_cache,
            )
            result = app.analyze_stock(job.symbol)
            job.result = result
            job.token_usage = result.get("token_usage") or {}
            job.llm_calls = int(result.get("llm_calls") or 0)
            if result.get("status") == "completed":
                job.state = "completed"
                job.stage = "Completed"
                job.progress = 1.0
            elif job.cancel_requested:
                job.state = "aborted"
                job.stage = "Aborted"
            else:
                job.state = "failed"
                job.error = result.get("error") or "analysis failed"
                job.stage = "Failed"
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            _logger.exception("analysis job %s failed", job.id)
            job.state = "aborted" if job.cancel_requested else "failed"
            job.stage = "Aborted" if job.cancel_requested else "Failed"
            job.error = None if job.cancel_requested else str(exc)
        finally:
            job.finished_at = _now()
            progress.set_active(None)
            self._persist(job)
            try:
                from .reports_index import write_run_status

                write_run_status(job.symbol, job.state)
            except Exception:  # status persistence is best-effort
                pass
            self._post_run_alerts_and_history(job)

    def _post_run_alerts_and_history(self, job: Job) -> None:
        """Fire alerts and capture a recommendation snapshot after a run."""
        try:
            import json as _json

            from . import _paths as _ap
            from .alerts import check_and_dispatch

            cur_rec = None
            prev_rec_data = None
            cur_p = _ap.recommendation_path(job.symbol)
            prev_p = _ap.prev_recommendation_path(job.symbol)
            if cur_p and cur_p.exists():
                cur_rec = _json.loads(cur_p.read_text(encoding="utf-8"))
            if prev_p and prev_p.exists():
                prev_rec_data = _json.loads(prev_p.read_text(encoding="utf-8"))
            check_and_dispatch(job.symbol, cur_rec, prev_rec_data)
            if job.state == "completed" and cur_rec:
                self._capture_rec_history(job, cur_rec)
        except Exception:
            pass

    def _capture_rec_history(self, job: Job, rec: Dict[str, Any]) -> None:
        """Append a recommendation snapshot (raw material for the scorecard)."""
        try:
            import json as _json

            from . import _paths as _ap
            from . import db

            price = None
            chart_p = _ap.chart_path(job.symbol)
            if chart_p and chart_p.exists():
                chart = _json.loads(chart_p.read_text(encoding="utf-8"))
                price = (chart.get("key_stats") or {}).get("current_price")
            db.record_recommendation(
                symbol=job.symbol,
                recorded_at=job.finished_at or _now(),
                recommendation=rec.get("recommendation"),
                target_price=_num(rec.get("target_price")),
                stop_loss=_num(rec.get("stop_loss")),
                confidence=_num(rec.get("confidence")),
                price_at_rec=_num(price),
            )
        except Exception:
            pass

    # ── startup recovery ─────────────────────────────────────────────────────
    def recover(self) -> None:
        """Reconcile with the DB after a restart: flag interrupted runs and
        re-enqueue anything that was still queued. Runs once."""
        with self._lock:
            if self._recovered:
                return
            self._recovered = True
        try:
            from . import db

            db.mark_orphaned_running()
            for row in db.queued_jobs():
                self.submit(
                    row["symbol"], row["depth"], row["asset_type"],
                    bool(row["use_cache"]), origin=row.get("origin") or "manual",
                )
        except Exception:
            _logger.debug("job recovery skipped", exc_info=True)

    # ── queries ─────────────────────────────────────────────────────────────
    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    @property
    def active_id(self) -> Optional[str]:
        with self._lock:
            return self._active_id

    @property
    def queue_depth(self) -> int:
        with self._lock:
            return len(self._pending)

    def queue_view(self) -> List[Dict[str, Any]]:
        """Active + pending jobs, in run order — for a queue/backlog display."""
        with self._lock:
            ids = ([self._active_id] if self._active_id else []) + list(self._pending)
        items = []
        for jid in ids:
            job = self._jobs.get(jid)
            if job is not None:
                items.append({
                    "id": job.id, "symbol": job.symbol, "depth": job.depth,
                    "origin": job.origin, "state": job.state, "created_at": job.created_at,
                })
        return items

    def live_view(self, job: Job) -> Dict[str, Any]:
        """Job state with live token/stage signals merged in while running."""
        token_usage = dict(job.token_usage)
        llm_calls = job.llm_calls
        stage = job.stage
        prog = job.progress
        activity = None
        if job.state == "running":
            # token_meter/llm_budget are global; the one running job owns them.
            try:
                from .. import token_meter
                from ..llm_budget import used as _used

                token_usage = token_meter.snapshot()
                llm_calls = _used()
            except Exception:  # pragma: no cover
                pass
            if job.tracker is not None:
                stage, prog = job.tracker.snapshot()
                activity = job.tracker.activity or None
        rec = None
        if job.result:
            rec = job.result.get("recommendation")
        return {
            "id": job.id,
            "symbol": job.symbol,
            "company_name": job.company_name,
            "depth": job.depth,
            "asset_type": job.asset_type,
            "origin": job.origin,
            "state": job.state,
            "stage": stage,
            "activity": activity,
            "progress": round(float(prog), 3),
            "queue_position": self._queue_position(job),
            "token_usage": token_usage,
            "llm_calls": llm_calls,
            "error": job.error,
            "result_ready": job.state == "completed",
            "recommendation": rec,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f  # drop NaN
    except (TypeError, ValueError):
        return None


# Module-level singleton used by the routes.
manager = JobManager()
