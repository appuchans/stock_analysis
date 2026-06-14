"""History gallery endpoint."""

from fastapi import APIRouter

from ..reports_index import list_reports
from ..schemas import HistoryItem, HistoryResponse

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history", response_model=HistoryResponse)
def history() -> HistoryResponse:
    return HistoryResponse(items=[HistoryItem(**it) for it in list_reports()])
