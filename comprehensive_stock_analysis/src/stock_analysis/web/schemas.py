"""Pydantic request/response models for the web API."""

import math
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..symbols import safe_symbol

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
    company_name: Optional[str] = None
    depth: str
    asset_type: str
    origin: str = "manual"
    state: Literal["queued", "running", "completed", "failed", "aborted", "interrupted"]
    stage: Optional[str] = None
    activity: Optional[str] = None
    progress: float = 0.0
    queue_position: int = 0
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


class QueueItem(BaseModel):
    id: str
    symbol: str
    depth: str
    origin: str = "manual"
    state: str
    created_at: Optional[str] = None


class QueueResponse(BaseModel):
    active_id: Optional[str] = None
    items: List[QueueItem]


class HistoryItem(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    status: str = "completed"  # completed | aborted | failed | incomplete
    asset_type: Optional[str] = None
    recommendation: Optional[str] = None
    target_price: Optional[float] = None
    confidence: Optional[Any] = None
    risk_level: Optional[str] = None
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    aum_bn: Optional[float] = None
    expense_ratio: Optional[float] = None
    distribution_yield: Optional[float] = None
    ytd_return: Optional[float] = None
    has_html: bool = False
    has_chart: bool = False
    spark: List[float] = Field(default_factory=list)
    mtime: Optional[str] = None


class HistoryResponse(BaseModel):
    items: List[HistoryItem]


class PortfolioRequest(BaseModel):
    symbols: List[str]
    period: str = "1y"
    risk_free_rate: float = Field(0.02, ge=0.0, le=0.2)
    weights: Optional[Dict[str, float]] = None

    @field_validator("symbols")
    @classmethod
    def _check_symbols(cls, v: List[str]) -> List[str]:
        import re

        cleaned = [(s or "").strip().upper() for s in v]
        for s in cleaned:
            if not re.match(_SYMBOL_RE, s):
                raise ValueError(f"invalid symbol: {s!r}")
        if len(cleaned) < 2:
            raise ValueError("at least 2 symbols required")
        if len(cleaned) > 20:
            raise ValueError("max 20 symbols")
        return cleaned

    @field_validator("weights")
    @classmethod
    def _check_weights(cls, v: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
        if v is None:
            return v
        normalized = {}
        for symbol, weight in v.items():
            normalized_symbol = safe_symbol(symbol)
            if not normalized_symbol:
                raise ValueError(f"invalid weight symbol: {symbol!r}")
            if not math.isfinite(weight) or weight < 0:
                raise ValueError("weights must be finite, non-negative values")
            normalized[normalized_symbol] = weight
        total = sum(normalized.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"weights must sum to 1.0 (got {total:.4f})")
        return normalized

    @model_validator(mode="after")
    def _weights_match_symbols(self) -> "PortfolioRequest":
        if self.weights is not None and set(self.weights) != set(self.symbols):
            raise ValueError("weights must contain exactly the requested symbols")
        return self


class PortfolioResponse(BaseModel):
    symbols: List[str]
    period: str
    correlation_matrix: Dict[str, Any]
    individual_metrics: Dict[str, Any]
    equal_weight_allocation: Dict[str, float]
    min_variance_weights: Dict[str, float]
    portfolio_weights: Dict[str, float]
    allocation_method: str
    portfolio_metrics: Dict[str, Any]


class WatchlistAddRequest(BaseModel):
    symbol: str
    notes: str = ""

    @field_validator("symbol")
    @classmethod
    def _normalize(cls, v: str) -> str:
        import re

        v = (v or "").strip().upper()
        if not re.match(_SYMBOL_RE, v):
            raise ValueError("invalid symbol")
        return v


class WatchlistItem(BaseModel):
    symbol: str
    added_at: str
    notes: str = ""


class WatchlistResponse(BaseModel):
    items: List[WatchlistItem]


class WatchlistAnalyzeRequest(BaseModel):
    depth: Literal["quick", "standard", "deep"] = "standard"
    use_cache: bool = True


class RecommendationDiff(BaseModel):
    has_diff: bool
    symbol: str
    message: Optional[str] = None
    current: Optional[Dict[str, Any]] = None
    previous: Optional[Dict[str, Any]] = None
    recommendation_changed: bool = False
    target_price_delta: Optional[float] = None
    confidence_delta: Optional[float] = None
    new_risks: List[str] = Field(default_factory=list)
    removed_risks: List[str] = Field(default_factory=list)
    new_opportunities: List[str] = Field(default_factory=list)
    removed_opportunities: List[str] = Field(default_factory=list)


class AlertItem(BaseModel):
    symbol: str
    timestamp: str
    reason: str
    old_rec: Optional[str] = None
    new_rec: Optional[str] = None
    old_confidence: Optional[float] = None
    new_confidence: Optional[float] = None


class AlertsResponse(BaseModel):
    items: List[AlertItem]


class RecHistoryItem(BaseModel):
    recorded_at: str
    recommendation: Optional[str] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    confidence: Optional[float] = None
    price_at_rec: Optional[float] = None


class RecHistoryResponse(BaseModel):
    symbol: str
    items: List[RecHistoryItem]


class AlertSettingsRequest(BaseModel):
    alert_email: Optional[str] = None
    alert_smtp_host: Optional[str] = None
    alert_smtp_port: Optional[int] = None
    alert_smtp_user: Optional[str] = None
    alert_smtp_password: Optional[str] = None
    alert_webhook_url: Optional[str] = None

    @field_validator("alert_webhook_url")
    @classmethod
    def _validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("alert_webhook_url must start with http:// or https://")
        return v


class AlertSettingsResponse(BaseModel):
    alert_email: str
    alert_smtp_host: str
    alert_smtp_port: int
    alert_smtp_user: str
    alert_smtp_password_set: bool
    alert_webhook_url: str
