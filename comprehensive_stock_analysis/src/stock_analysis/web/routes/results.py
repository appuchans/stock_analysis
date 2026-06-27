"""Serve a symbol's self-contained HTML report and chart-data JSON."""

import json
from typing import Any, Dict

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


@router.get("/{symbol}/diff")
def recommendation_diff(symbol: str) -> Dict[str, Any]:
    sym = _paths.safe_symbol(symbol)
    if sym is None:
        raise HTTPException(status_code=400, detail="invalid symbol")

    cur_path = _paths.recommendation_path(symbol)
    if cur_path is None or not cur_path.exists():
        raise HTTPException(status_code=404, detail="recommendation not found")

    prev_path = _paths.prev_recommendation_path(symbol)
    if prev_path is None or not prev_path.exists():
        return {"has_diff": False, "symbol": sym, "message": "Only one run available"}

    try:
        cur = json.loads(cur_path.read_text(encoding="utf-8"))
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to parse recommendation files: {exc}")

    def _to_float(v: Any):
        try:
            f = float(v)
            return None if f != f else f
        except (TypeError, ValueError):
            return None

    cur_price = _to_float(cur.get("target_price"))
    prev_price = _to_float(prev.get("target_price"))
    cur_conf = _to_float(cur.get("confidence"))
    prev_conf = _to_float(prev.get("confidence"))

    cur_risks = list(cur.get("risks") or [])
    prev_risks = list(prev.get("risks") or [])
    cur_opps = list(cur.get("opportunities") or [])
    prev_opps = list(prev.get("opportunities") or [])

    return {
        "has_diff": True,
        "symbol": sym,
        "current": {
            "recommendation": cur.get("recommendation"),
            "target_price": cur_price,
            "confidence": cur_conf,
            "risk_level": cur.get("risk_level"),
        },
        "previous": {
            "recommendation": prev.get("recommendation"),
            "target_price": prev_price,
            "confidence": prev_conf,
            "risk_level": prev.get("risk_level"),
        },
        "recommendation_changed": cur.get("recommendation") != prev.get("recommendation"),
        "target_price_delta": (cur_price - prev_price)
            if cur_price is not None and prev_price is not None else None,
        "confidence_delta": (cur_conf - prev_conf)
            if cur_conf is not None and prev_conf is not None else None,
        "new_risks": [r for r in cur_risks if r not in prev_risks],
        "removed_risks": [r for r in prev_risks if r not in cur_risks],
        "new_opportunities": [o for o in cur_opps if o not in prev_opps],
        "removed_opportunities": [o for o in prev_opps if o not in cur_opps],
    }
