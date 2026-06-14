"""Pydantic request/response models for the web API."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Ticker / fund symbol: 1–10 chars, uppercase letters, digits, dot, hyphen.
_SYMBOL_RE = r"^[A-Z][A-Z0-9.\-]{0,9}$"


class AnalyzeRequest(BaseModel):
    """Body for POST /api/analyze."""

    symbol: str
    depth: Literal["quick", "standard", "deep"] = "standard"
    asset_type: Literal["auto", "stock", "etf"] = "auto"
    use_cache: bool = True

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        import re

        v = (v or "").strip().upper()
        if not re.match(_SYMBOL_RE, v):
            raise ValueError("symbol must be 1–10 chars: letters, digits, '.', '-'")
        return v


class JobState(BaseModel):
    """Snapshot returned by GET /api/jobs/{id}."""

    id: str
    symbol: str
    depth: str
    asset_type: str
    state: Literal["queued", "running", "completed", "failed"]
    stage: Optional[str] = None
    progress: float = 0.0
    token_usage: Dict[str, int] = Field(default_factory=dict)
    llm_calls: int = 0
    error: Optional[str] = None
    result_ready: bool = False
    recommendation: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class AnalyzeResponse(BaseModel):
    job_id: str
    state: str


class HistoryItem(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    recommendation: Optional[str] = None
    target_price: Optional[float] = None
    confidence: Optional[Any] = None
    risk_level: Optional[str] = None
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    has_html: bool = False
    has_chart: bool = False
    mtime: Optional[str] = None


class HistoryResponse(BaseModel):
    items: List[HistoryItem]
