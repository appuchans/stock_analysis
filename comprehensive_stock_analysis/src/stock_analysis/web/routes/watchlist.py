"""Watchlist CRUD endpoints."""

import re

from fastapi import APIRouter, HTTPException

from .. import db
from ..jobs import JobConflictError, manager
from ..schemas import (
    _SYMBOL_RE,
    WatchlistAddRequest,
    WatchlistAnalyzeRequest,
    WatchlistItem,
    WatchlistResponse,
)

router = APIRouter(prefix="/api", tags=["watchlist"])


@router.get("/watchlist", response_model=WatchlistResponse)
def list_watchlist() -> WatchlistResponse:
    return WatchlistResponse(items=[WatchlistItem(**row) for row in db.list_symbols()])


@router.post("/watchlist", response_model=WatchlistItem, status_code=201)
def add_to_watchlist(req: WatchlistAddRequest) -> WatchlistItem:
    added = db.add_symbol(req.symbol, req.notes)
    if not added:
        raise HTTPException(status_code=409, detail="symbol already in watchlist")
    rows = db.list_symbols()
    row = next((r for r in rows if r["symbol"] == req.symbol), None)
    if row is None:
        raise HTTPException(status_code=500, detail="failed to retrieve added symbol")
    return WatchlistItem(**row)


@router.delete("/watchlist/{symbol}", status_code=204)
def remove_from_watchlist(symbol: str) -> None:
    symbol = symbol.upper()
    if not re.match(_SYMBOL_RE, symbol):
        raise HTTPException(status_code=400, detail="invalid symbol")
    removed = db.remove_symbol(symbol)
    if not removed:
        raise HTTPException(status_code=404, detail="symbol not found in watchlist")


@router.post("/watchlist/analyze", status_code=202)
def analyze_watchlist(req: WatchlistAnalyzeRequest) -> dict:
    symbols = [row["symbol"] for row in db.list_symbols()]
    if not symbols:
        raise HTTPException(status_code=400, detail="watchlist is empty")
    first = symbols[0]
    rest = symbols[1:]
    try:
        job = manager.submit(first, req.depth, "auto", req.use_cache)
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    result: dict = {"queued": [first], "job_id": job.id, "state": job.state}
    if rest:
        result["skipped"] = rest
        result["reason"] = "one at a time"
    return result
