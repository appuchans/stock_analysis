"""Portfolio analysis endpoint."""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..schemas import PortfolioRequest
from ...tools.portfolio_tools import PortfolioAnalysisTool

router = APIRouter(prefix="/api", tags=["portfolio"])

_tool = PortfolioAnalysisTool()


@router.post("/portfolio/analyze")
def analyze_portfolio(req: PortfolioRequest) -> Dict[str, Any]:
    result = _tool._run(req.symbols, req.period, req.risk_free_rate, req.weights)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
