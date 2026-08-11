"""FIFO cost-basis engine for portfolio holdings — pure functions over a list
of transaction dicts, no I/O. Transactions are the source of truth; positions
(open quantity, average cost, realized P&L) are always derived fresh from
them rather than stored, so a corrected or re-imported transaction history
never leaves stale numbers behind.
"""

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

_EPS = 1e-9


def compute_positions(transactions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Derive one position per symbol from its full transaction history.

    Each symbol's transactions are walked oldest-first; buys push a lot onto
    a FIFO queue (fees folded into that lot's per-share cost basis), sells
    consume the oldest lots first and accumulate realized P&L (fees folded
    into the sale's per-share proceeds). A sell that exceeds all open lots
    (short position) stops consuming once lots are exhausted — this ledger
    is long-only.
    """
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for t in transactions:
        by_symbol.setdefault(t["symbol"], []).append(t)

    positions: Dict[str, Dict[str, Any]] = {}
    for symbol, txs in by_symbol.items():
        ordered = sorted(txs, key=lambda t: (t["date"], t.get("id") or 0))
        lots: deque = deque()
        realized_pnl = 0.0

        for t in ordered:
            qty = float(t["qty"])
            price = float(t["price"])
            fees = float(t.get("fees") or 0)
            if qty <= 0:
                continue
            if t["side"] == "buy":
                per_share_cost = price + (fees / qty)
                lots.append(
                    {"qty": qty, "cost_basis": per_share_cost, "date": t["date"]}
                )
            elif t["side"] == "sell":
                remaining = qty
                proceeds_per_share = price - (fees / qty)
                while remaining > _EPS and lots:
                    lot = lots[0]
                    consumed = min(lot["qty"], remaining)
                    realized_pnl += consumed * (proceeds_per_share - lot["cost_basis"])
                    lot["qty"] -= consumed
                    remaining -= consumed
                    if lot["qty"] <= _EPS:
                        lots.popleft()

        open_qty = sum(lot["qty"] for lot in lots)
        cost_basis_total = sum(lot["qty"] * lot["cost_basis"] for lot in lots)
        avg_cost = (cost_basis_total / open_qty) if open_qty > _EPS else 0.0

        positions[symbol] = {
            "symbol": symbol,
            "qty": round(open_qty, 6),
            "avg_cost": round(avg_cost, 4),
            "cost_basis_total": round(cost_basis_total, 2),
            "realized_pnl": round(realized_pnl, 2),
            "lots": [
                {
                    "qty": round(lot["qty"], 6),
                    "cost_basis": round(lot["cost_basis"], 4),
                    "date": lot["date"],
                }
                for lot in lots
            ],
        }
    return positions


def parse_transactions_csv(text: str) -> List[Dict[str, Any]]:
    """Parse a generic broker-export CSV: date,symbol,side,qty,price[,fees][,note].
    Returns a list of transaction dicts ready for db.add_transaction, or raises
    ValueError with a line-numbered message on the first malformed row.
    """
    import csv
    import io

    from ..symbols import safe_symbol

    reader = csv.DictReader(io.StringIO(text.strip()))
    required = {"date", "symbol", "side", "qty", "price"}
    if reader.fieldnames is None or not required.issubset(
        {f.strip().lower() for f in reader.fieldnames}
    ):
        raise ValueError(f"CSV header must include: {', '.join(sorted(required))}")

    rows: List[Dict[str, Any]] = []
    for i, raw in enumerate(reader, start=2):  # header is line 1
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        symbol = safe_symbol(row.get("symbol", ""))
        if not symbol:
            raise ValueError(f"line {i}: invalid symbol {row.get('symbol')!r}")
        side = row.get("side", "").lower()
        if side not in ("buy", "sell"):
            raise ValueError(
                f"line {i}: side must be 'buy' or 'sell', got {row.get('side')!r}"
            )
        try:
            qty = float(row["qty"])
            price = float(row["price"])
            fees = float(row["fees"]) if row.get("fees") else 0.0
        except ValueError as exc:
            raise ValueError(f"line {i}: non-numeric qty/price/fees ({exc})")
        if qty <= 0 or price < 0:
            raise ValueError(f"line {i}: qty must be positive and price non-negative")
        date = row.get("date", "")
        if not date:
            raise ValueError(f"line {i}: date is required")
        rows.append(
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "fees": fees,
                "date": date,
                "note": row.get("note", ""),
            }
        )
    return rows


def build_value_series(transactions: List[Dict[str, Any]], prices: "Any") -> "Any":
    """Reconstruct historical portfolio value from transactions x daily closes.

    ``prices`` is a pandas DataFrame indexed by date with one column per held
    symbol (as returned by e.g. ``yf.download(symbols)["Close"]``). For each
    symbol, the quantity held is a step function that changes only on
    transaction dates (buys add, sells subtract) — that cumulative quantity is
    forward-filled across ``prices``' full date range and multiplied by that
    day's close, then summed across symbols. Symbols with a transaction but no
    matching price column are silently skipped (e.g. a delisted ticker).

    Returns a pandas Series of portfolio value indexed by date; empty if there
    are no transactions or no overlapping price data.
    """
    import pandas as pd

    if not transactions or prices is None or len(prices) == 0:
        return pd.Series(dtype=float)

    changes_by_symbol: Dict[str, Dict[str, float]] = defaultdict(dict)
    for t in transactions:
        signed = float(t["qty"]) if t["side"] == "buy" else -float(t["qty"])
        d = t["date"]
        changes_by_symbol[t["symbol"]][d] = (
            changes_by_symbol[t["symbol"]].get(d, 0.0) + signed
        )

    qty_columns: Dict[str, "Any"] = {}
    for symbol, changes in changes_by_symbol.items():
        if symbol not in prices.columns:
            continue
        s = pd.Series(changes)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index().cumsum()
        qty_columns[symbol] = s.reindex(prices.index, method="ffill").fillna(0)

    if not qty_columns:
        return pd.Series(dtype=float)

    qty_df = pd.DataFrame(qty_columns).fillna(0)
    value = (qty_df * prices[qty_df.columns]).sum(axis=1)
    return value[
        value.index
        >= min(
            pd.to_datetime(d)
            for d in (c for changes in changes_by_symbol.values() for c in changes)
        )
    ]


def compute_benchmark_comparison(
    portfolio_value: "Any",
    benchmark_prices: "Any",
    risk_free_rate: float = 0.02,
) -> Dict[str, Any]:
    """Index both series to 100 at their common start date and compute
    alpha/beta/Sharpe for the portfolio vs the benchmark. Both inputs are
    pandas Series indexed by date. Returns {} when there's insufficient
    overlapping history (fewer than 5 common trading days) to mean anything.
    """
    import numpy as np

    common = portfolio_value.index.intersection(benchmark_prices.index)
    pv = portfolio_value.reindex(common).dropna()
    bp = benchmark_prices.reindex(common).dropna()
    common = pv.index.intersection(bp.index)
    pv, bp = pv.reindex(common), bp.reindex(common)
    if len(pv) < 5 or pv.iloc[0] <= 0 or bp.iloc[0] <= 0:
        return {}

    port_ret = pv.pct_change().dropna()
    bench_ret = bp.pct_change().dropna()
    ret_common = port_ret.index.intersection(bench_ret.index)
    port_ret, bench_ret = port_ret.reindex(ret_common), bench_ret.reindex(ret_common)
    if len(port_ret) < 2:
        return {}

    cov = np.cov(port_ret.values, bench_ret.values)
    bench_var = cov[1, 1]
    beta: Optional[float] = float(cov[0, 1] / bench_var) if bench_var > 0 else None

    ann_port_ret = float(port_ret.mean() * 252)
    ann_bench_ret = float(bench_ret.mean() * 252)
    alpha: Optional[float] = (
        ann_port_ret - (risk_free_rate + beta * (ann_bench_ret - risk_free_rate))
        if beta is not None
        else None
    )
    ann_vol = float(port_ret.std() * np.sqrt(252))
    sharpe: Optional[float] = (
        (ann_port_ret - risk_free_rate) / ann_vol if ann_vol > 0 else None
    )

    pv_indexed = (pv / pv.iloc[0] * 100).round(2)
    bp_indexed = (bp / bp.iloc[0] * 100).round(2)

    return {
        "portfolio_indexed": [
            {"date": d.strftime("%Y-%m-%d"), "value": float(v)}
            for d, v in pv_indexed.items()
        ],
        "benchmark_indexed": [
            {"date": d.strftime("%Y-%m-%d"), "value": float(v)}
            for d, v in bp_indexed.items()
        ],
        "alpha_annualized_pct": round(alpha * 100, 2) if alpha is not None else None,
        "beta": round(beta, 3) if beta is not None else None,
        "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
    }
