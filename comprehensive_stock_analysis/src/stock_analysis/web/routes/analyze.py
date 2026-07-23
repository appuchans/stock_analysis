"""Run-submission and job-status endpoints."""

from fastapi import APIRouter, HTTPException

from ..jobs import manager
from ..schemas import AnalyzeRequest, AnalyzeResponse, JobState, QueueResponse

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
def submit_analysis(req: AnalyzeRequest) -> AnalyzeResponse:
    job = manager.submit(req.symbol, req.depth, req.asset_type, req.use_cache)
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
