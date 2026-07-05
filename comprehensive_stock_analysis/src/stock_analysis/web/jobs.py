"""Single-worker job queue for serialized analysis runs.

Runs MUST be serialized: ``token_meter`` and ``llm_budget`` are process-global
and reset at the start of each run, so two concurrent in-process analyses would
corrupt each other's accounting. A ``ThreadPoolExecutor(max_workers=1)`` is the
serialization point; a second submit while one is active is rejected (409).

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
from typing import Any, Dict, Optional

from . import progress

_logger = logging.getLogger(__name__)

_ACTIVE_STATES = ("queued", "running")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class JobConflictError(RuntimeError):
    """Raised when a run is requested while another is queued/running."""


@dataclass
class Job:
    id: str
    symbol: str
    depth: str
    asset_type: str
    use_cache: bool
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
    """Owns the single worker and the in-memory job registry (single-user)."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
        self._jobs: Dict[str, Job] = {}
        self._active_id: Optional[str] = None
        self._lock = threading.Lock()

    # ── submission ──────────────────────────────────────────────────────────
    def submit(self, symbol: str, depth: str, asset_type: str, use_cache: bool) -> Job:
        with self._lock:
            if self._active_id is not None:
                active = self._jobs.get(self._active_id)
                if active and active.state in _ACTIVE_STATES:
                    raise JobConflictError(f"analysis already in progress for {active.symbol}")
            job = Job(
                id=uuid.uuid4().hex,
                symbol=symbol,
                depth=depth,
                asset_type=asset_type,
                use_cache=use_cache,
            )
            self._jobs[job.id] = job
            self._active_id = job.id
        self._executor.submit(self._run, job)
        return job

    # ── worker (runs in the single worker thread) ───────────────────────────
    def cancel(self, job_id: str):
        """Request cancellation of a job. Returns None (unknown), False (not
        active / nothing to cancel), or True (cancellation requested)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.state not in _ACTIVE_STATES:
                return False
            job.cancel_requested = True
        from ..llm_budget import request_abort

        request_abort()
        _logger.info("cancellation requested for job %s (%s)", job_id, job.symbol)
        return True

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
            try:
                from .reports_index import write_run_status

                write_run_status(job.symbol, job.state)
            except Exception:  # status persistence is best-effort
                pass
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
            except Exception:
                pass
            with self._lock:
                if self._active_id == job.id:
                    self._active_id = None

    # ── queries ─────────────────────────────────────────────────────────────
    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    @property
    def active_id(self) -> Optional[str]:
        with self._lock:
            return self._active_id

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
            "state": job.state,
            "stage": stage,
            "activity": activity,
            "progress": round(float(prog), 3),
            "token_usage": token_usage,
            "llm_calls": llm_calls,
            "error": job.error,
            "result_ready": job.state == "completed",
            "recommendation": rec,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }


# Module-level singleton used by the routes.
manager = JobManager()
