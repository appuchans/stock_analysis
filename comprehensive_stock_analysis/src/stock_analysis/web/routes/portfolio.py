"""Portfolio analysis, holdings ledger (transactions -> FIFO positions), and
live-priced position enrichment."""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import (
    CSVImportRequest,
    CSVImportResponse,
    PortfolioRequest,
    PositionItem,
    TransactionCreateRequest,
    TransactionItem,
)
from ...tools.portfolio_tools import PortfolioAnalysisTool

router = APIRouter(prefix="/api", tags=["portfolio"])

_tool = PortfolioAnalysisTool()


@router.post("/portfolio/analyze")
def analyze_portfolio(req: PortfolioRequest) -> Dict[str, Any]:
    weights = req.weights if req.weights is not None else _holdings_weights(req.symbols)
    result = _tool._run(req.symbols, req.period, req.risk_free_rate, weights)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


def _holdings_weights(symbols: List[str]) -> Any:
    """When every requested symbol has an open position, weight the analysis
    by actual holdings (cost basis) instead of leaving it to the optimizer —
    "how is MY portfolio doing" rather than "how should it be allocated".
    Returns None (defer to the optimizer) unless every symbol is held."""
    from ...tools.portfolio_ledger import compute_positions

    positions = compute_positions(db.list_transactions())
    held = {s: positions[s] for s in symbols if s in positions and positions[s]["qty"] > 1e-9}
    if len(held) != len(symbols):
        return None
    total_cost = sum(p["cost_basis_total"] for p in held.values())
    if total_cost <= 0:
        return None
    return {s: round(p["cost_basis_total"] / total_cost, 4) for s, p in held.items()}


# ── Transactions ─────────────────────────────────────────────────────────────
@router.get("/portfolio/transactions", response_model=List[TransactionItem])
def list_transactions() -> List[dict]:
    return db.list_transactions()


@router.post("/portfolio/transactions", response_model=TransactionItem, status_code=201)
def create_transaction(req: TransactionCreateRequest) -> dict:
    tx_id = db.add_transaction(req.model_dump())
    return next(t for t in db.list_transactions(req.symbol) if t["id"] == tx_id)


@router.delete("/portfolio/transactions/{tx_id}", status_code=204)
def delete_transaction(tx_id: int) -> None:
    if not db.delete_transaction(tx_id):
        raise HTTPException(status_code=404, detail="unknown transaction id")


@router.post("/portfolio/transactions/import", response_model=CSVImportResponse)
def import_transactions_csv(req: CSVImportRequest) -> dict:
    from ...tools.portfolio_ledger import parse_transactions_csv

    try:
        rows = parse_transactions_csv(req.csv)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not rows:
        raise HTTPException(status_code=422, detail="no transaction rows found in CSV")
    count = db.add_transactions(rows)
    return {"imported": count}


# ── Positions (derived from transactions, enriched with a live quote) ────────
@router.get("/portfolio/positions", response_model=List[PositionItem])
def list_positions() -> List[dict]:
    from ...tools.portfolio_ledger import compute_positions

    txs = db.list_transactions()
    positions = compute_positions(txs)
    return [p for p in positions.values() if p["qty"] > 1e-9]


# ── Dashboard (live-priced positions + historical value + benchmark) ─────────
@router.get("/portfolio/dashboard")
def portfolio_dashboard(benchmark: str = "SPY") -> Dict[str, Any]:
    """Everything the portfolio view needs in one call: live-priced positions
    (market value, unrealized P&L, weight), realized P&L, a reconstructed
    historical value series, and a benchmark comparison (alpha/beta/Sharpe).
    History/benchmark are best-effort — positions still return if the price
    history fetch fails."""
    from ...tools.portfolio_ledger import (
        build_value_series,
        compute_benchmark_comparison,
        compute_positions,
    )
    from ...tools.providers import ROUTER

    txs = db.list_transactions()
    positions = compute_positions(txs)
    open_positions = {s: p for s, p in positions.items() if p["qty"] > 1e-9}
    empty: Dict[str, Any] = {
        "positions": [], "total_market_value": 0.0, "total_cost_basis": 0.0,
        "total_unrealized_pnl": 0.0, "total_realized_pnl": 0.0,
        "value_series": [], "benchmark_symbol": benchmark, "benchmark_comparison": None,
    }
    if not open_positions:
        return empty

    symbols = list(open_positions.keys())
    quotes: Dict[str, Any] = ROUTER.get_batch_quotes(symbols)
    for s in symbols:
        if s not in quotes:
            q = ROUTER.get_quote(s)
            if q:
                quotes[s] = q

    enriched = []
    total_value = 0.0
    total_cost = 0.0
    total_realized = 0.0
    for s, p in open_positions.items():
        q = quotes.get(s) or {}
        price = q.get("price")
        market_value = (price * p["qty"]) if price is not None else None
        unrealized = (market_value - p["cost_basis_total"]) if market_value is not None else None
        total_value += market_value or 0.0
        total_cost += p["cost_basis_total"]
        total_realized += p["realized_pnl"]
        enriched.append({
            "symbol": s, "qty": p["qty"], "avg_cost": p["avg_cost"],
            "cost_basis_total": p["cost_basis_total"], "realized_pnl": p["realized_pnl"],
            "current_price": price, "market_value": round(market_value, 2) if market_value is not None else None,
            "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
            "day_change_pct": q.get("change_pct"),
        })
    for e in enriched:
        e["weight"] = (
            round(e["market_value"] / total_value, 4)
            if total_value and e["market_value"] is not None else None
        )
    enriched.sort(key=lambda e: -(e["market_value"] or 0))

    value_series_data: List[Dict[str, Any]] = []
    benchmark_comparison = None
    try:
        import pandas as pd
        import yfinance as yf

        earliest = min(t["date"] for t in txs if t["symbol"] in open_positions)
        hist_symbols = symbols + [benchmark]
        raw = yf.download(hist_symbols, start=earliest, progress=False, auto_adjust=True)["Close"]
        if isinstance(raw, pd.Series):
            raw = raw.to_frame(hist_symbols[0])
        value_series = build_value_series(txs, raw[[c for c in symbols if c in raw.columns]])
        value_series_data = [
            {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 2)} for d, v in value_series.items()
        ]
        if benchmark in raw.columns and not value_series.empty:
            benchmark_comparison = compute_benchmark_comparison(value_series, raw[benchmark].dropna()) or None
    except Exception:
        pass  # history/benchmark are best-effort; positions above still return

    return {
        "positions": enriched,
        "total_market_value": round(total_value, 2),
        "total_cost_basis": round(total_cost, 2),
        "total_unrealized_pnl": round(total_value - total_cost, 2) if total_value else None,
        "total_realized_pnl": round(total_realized, 2),
        "value_series": value_series_data,
        "benchmark_symbol": benchmark,
        "benchmark_comparison": benchmark_comparison,
    }
