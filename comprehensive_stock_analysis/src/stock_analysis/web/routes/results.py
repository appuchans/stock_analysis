"""Serve a symbol's self-contained HTML report and chart-data JSON."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import _paths

router = APIRouter(prefix="/api/reports", tags=["results"])


@router.get("/{symbol}/html")
def report_html(symbol: str) -> FileResponse:
    path = _paths.html_path(symbol)
    if path is None:
        raise HTTPException(status_code=404, detail="invalid symbol")
    if not path.exists():
        raise HTTPException(status_code=404, detail="report not found")
    return FileResponse(path, media_type="text/html")


@router.get("/{symbol}/chart")
def report_chart(symbol: str) -> FileResponse:
    path = _paths.chart_path(symbol)
    if path is None:
        raise HTTPException(status_code=404, detail="invalid symbol")
    if not path.exists():
        raise HTTPException(status_code=404, detail="chart data not found")
    return FileResponse(path, media_type="application/json")
