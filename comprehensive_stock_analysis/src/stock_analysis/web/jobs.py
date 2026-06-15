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


def _n_specialists(depth: str, is_etf: bool) -> int:
    """Specialist-stage count, mirroring flow_crew._stages_for (stock vs ETF)."""
    if depth == "quick":
        return 1
    if depth == "standard":
        return 3 if is_etf else 4
    return 7 if is_etf else 9  # deep


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
                    raise JobConflictError(
                        f"analysis already in progress for {active.symbol}"
                    )
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
        from ..llm_budget import AnalysisAbortedError
        from ..main import StockAnalysisApp

        job.state = "running"
        job.started_at = _now()
        is_etf = job.asset_type == "etf"
        job.tracker = progress.StageTracker(_n_specialists(job.depth, is_etf))
        progress.set_active(job.tracker)
        try:
            app = StockAnalysisApp(
                depth=job.depth,
                asset_type=job.asset_type,
                use_data_cache=job.use_cache,
            )
            result = app.analyze_stock(job.symbol)
            job.result = result
            job.token_usage = result.get("token_usage") or {}
            job.llm_calls = int(result.get("llm_calls") or 0)
            if job.cancel_requested:
                job.state = "aborted"
                job.stage = "Aborted"
            elif result.get("status") == "completed":
                job.state = "completed"
                job.stage = "Completed"
                job.progress = 1.0
            else:
                job.state = "failed"
                job.error = result.get("error") or "analysis failed"
                job.stage = "Failed"
        except AnalysisAbortedError:
            job.state = "aborted"
            job.stage = "Aborted"
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
        rec = None
        if job.result:
            rec = job.result.get("recommendation")
        return {
            "id": job.id,
            "symbol": job.symbol,
            "depth": job.depth,
            "asset_type": job.asset_type,
            "state": job.state,
            "stage": stage,
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
