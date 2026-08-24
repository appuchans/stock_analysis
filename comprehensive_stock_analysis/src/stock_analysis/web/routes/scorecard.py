"""Recommendation scorecard endpoint."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..db import list_all_rec_history
from ..scorecard import build_scorecard

router = APIRouter(prefix="/api", tags=["scorecard"])


class ScorecardSummary(BaseModel):
    total: int
    graded: int
    correct: int
    accuracy_pct: Optional[float] = None


class ScorecardItem(BaseModel):
    symbol: str
    recorded_at: Optional[str] = None
    recommendation: Optional[str] = None
    confidence: Optional[float] = None
    price_at_rec: Optional[float] = None
    returns: Dict[str, Any] = {}
    grade: Optional[str] = None


class ScorecardResponse(BaseModel):
    summary: ScorecardSummary
    items: List[ScorecardItem]


@router.get("/scorecard", response_model=ScorecardResponse)
def scorecard() -> ScorecardResponse:
    """Grade every recorded recommendation against realized forward returns."""
    result = build_scorecard(list_all_rec_history())
    return ScorecardResponse(**result)
