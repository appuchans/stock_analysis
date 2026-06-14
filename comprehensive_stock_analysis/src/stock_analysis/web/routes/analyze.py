"""Run-submission and job-status endpoints."""

from fastapi import APIRouter, HTTPException

from ..jobs import JobConflictError, manager
from ..schemas import AnalyzeRequest, AnalyzeResponse, JobState

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
def submit_analysis(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        job = manager.submit(req.symbol, req.depth, req.asset_type, req.use_cache)
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return AnalyzeResponse(job_id=job.id, state=job.state)


@router.get("/jobs/{job_id}", response_model=JobState)
def job_status(job_id: str) -> JobState:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job id")
    return JobState(**manager.live_view(job))
