"""Run-submission and job-status endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from ...config.settings import settings
from ..jobs import manager
from ..schemas import AnalyzeRequest, AnalyzeResponse, JobState, QueueResponse

router = APIRouter(prefix="/api", tags=["analyze"])


def _hours_since_last_run(symbol: str) -> Optional[float]:
    """Age of the last *completed* analysis, or None.

    Aborted/failed runs return None on purpose — retrying those immediately is
    exactly what a user should be able to do.
    """
    try:
        from .. import _paths
        from ..reports_index import _analyzed_at, _read_json

        status = _read_json(_paths.status_path(symbol)) or {}
        if status.get("status") not in (None, "completed"):
            return None
        stamp = _analyzed_at(symbol, status)
        if not stamp:
            return None
        return (datetime.now() - datetime.fromisoformat(stamp)).total_seconds() / 3600
    except Exception:  # a freshness check must never block a run
        return None


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
def submit_analysis(req: AnalyzeRequest) -> AnalyzeResponse:
    # A full analysis costs a full set of LLM calls and the underlying data
    # barely moves within a day, so an accidental Refresh minutes after a run
    # is almost always a mistake. Only manual submissions reach this route —
    # scheduled and watchlist runs call manager.submit directly — so no
    # origin check is needed here.
    window = settings.min_rerun_interval_hours
    if window > 0 and not req.force and not req.resume:
        age = _hours_since_last_run(req.symbol)
        if age is not None and age < window:
            raise HTTPException(
                status_code=409,
                detail=f"{req.symbol} was analyzed {age:.1f} hours ago.",
            )

    job = manager.submit(
        req.symbol, req.depth, req.asset_type, req.use_cache, resume=req.resume
    )
    return AnalyzeResponse(job_id=job.id, state=job.state)


@router.get("/jobs", response_model=QueueResponse)
def list_queue() -> QueueResponse:
    """Active + queued jobs, in run order (for a backlog/queue display)."""
    return QueueResponse(active_id=manager.active_id, items=manager.queue_view())


@router.get("/jobs/{job_id}", response_model=JobState)
def job_status(job_id: str) -> JobState:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job id")
    return JobState(**manager.live_view(job))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    result = manager.cancel(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown job id")
    if result is False:
        raise HTTPException(status_code=409, detail="job is not active")
    return {"job_id": job_id, "state": "cancelling"}
