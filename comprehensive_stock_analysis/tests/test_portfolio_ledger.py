"""Tests for tools/portfolio_ledger.py: FIFO cost-basis computation, CSV
transaction import parsing, historical value reconstruction, and benchmark
comparison."""

import pandas as pd
import pytest

from src.stock_analysis.tools.portfolio_ledger import (
    build_value_series,
    compute_benchmark_comparison,
    compute_positions,
    parse_transactions_csv,
)


def _tx(symbol, side, qty, price, fees=0.0, date="2026-01-01", tx_id=None):
    return {
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "fees": fees,
        "date": date,
        "id": tx_id,
    }


class TestComputePositionsBasic:
    def test_single_buy_creates_open_position(self):
        positions = compute_positions([_tx("AAPL", "buy", 10, 100.0)])
        p = positions["AAPL"]
        assert p["qty"] == 10
        assert p["avg_cost"] == 100.0
        assert p["cost_basis_total"] == 1000.0
        assert p["realized_pnl"] == 0.0

    def test_fees_are_folded_into_cost_basis(self):
        positions = compute_positions([_tx("AAPL", "buy", 10, 100.0, fees=10.0)])
        p = positions["AAPL"]
        # $10 fee / 10 shares = $1/share added to the $100 price.
        assert p["avg_cost"] == 101.0
        assert p["cost_basis_total"] == 1010.0

    def test_two_buys_average_cost_correctly(self):
        positions = compute_positions(
            [
                _tx("AAPL", "buy", 10, 100.0, date="2026-01-01"),
                _tx("AAPL", "buy", 10, 120.0, date="2026-01-02"),
            ]
        )
        p = positions["AAPL"]
        assert p["qty"] == 20
        assert p["avg_cost"] == 110.0
        assert p["cost_basis_total"] == 2200.0


class TestFIFOSelling:
    def test_full_sell_realizes_pnl_and_closes_position(self):
        positions = compute_positions(
            [
                _tx("AAPL", "buy", 10, 100.0, date="2026-01-01"),
                _tx("AAPL", "sell", 10, 150.0, date="2026-02-01"),
            ]
        )
        p = positions["AAPL"]
        assert p["qty"] == 0
        assert p["realized_pnl"] == 500.0  # (150-100)*10
        assert p["lots"] == []

    def test_partial_sell_consumes_oldest_lot_first(self):
        positions = compute_positions(
            [
                _tx("AAPL", "buy", 10, 100.0, date="2026-01-01"),
                _tx("AAPL", "buy", 10, 200.0, date="2026-01-15"),
                _tx("AAPL", "sell", 10, 250.0, date="2026-02-01"),
            ]
        )
        p = positions["AAPL"]
        # FIFO: the 10 sold shares come from the $100 lot, not the $200 one.
        assert p["qty"] == 10
        assert p["avg_cost"] == 200.0
        assert p["realized_pnl"] == 1500.0  # (250-100)*10

    def test_sell_spanning_two_lots(self):
        positions = compute_positions(
            [
                _tx("AAPL", "buy", 5, 100.0, date="2026-01-01"),
                _tx("AAPL", "buy", 5, 200.0, date="2026-01-15"),
                _tx("AAPL", "sell", 8, 300.0, date="2026-02-01"),
            ]
        )
        p = positions["AAPL"]
        # 5 shares @ $100 + 3 shares @ $200 consumed.
        assert p["qty"] == pytest.approx(2)
        assert p["realized_pnl"] == pytest.approx((300 - 100) * 5 + (300 - 200) * 3)
        assert p["lots"][0]["cost_basis"] == 200.0
        assert p["lots"][0]["qty"] == pytest.approx(2)

    def test_sell_fees_reduce_proceeds(self):
        positions = compute_positions(
            [
                _tx("AAPL", "buy", 10, 100.0, date="2026-01-01"),
                _tx("AAPL", "sell", 10, 150.0, fees=20.0, date="2026-02-01"),
            ]
        )
        p = positions["AAPL"]
        # $20 fee / 10 shares = $2/share off the $150 sale price.
        assert p["realized_pnl"] == pytest.approx((148 - 100) * 10)

    def test_sell_exceeding_open_lots_stops_at_zero(self):
        """Long-only ledger: an oversell just exhausts available lots rather
        than going negative or raising."""
        positions = compute_positions(
            [
                _tx("AAPL", "buy", 5, 100.0, date="2026-01-01"),
                _tx("AAPL", "sell", 10, 150.0, date="2026-02-01"),
            ]
        )
        p = positions["AAPL"]
        assert p["qty"] == 0
        assert p["realized_pnl"] == pytest.approx((150 - 100) * 5)


class TestComputePositionsMultiSymbol:
    def test_multiple_symbols_are_independent(self):
        positions = compute_positions(
            [
                _tx("AAPL", "buy", 10, 100.0, date="2026-01-01"),
                _tx("MSFT", "buy", 5, 300.0, date="2026-01-01"),
            ]
        )
        assert set(positions) == {"AAPL", "MSFT"}
        assert positions["AAPL"]["qty"] == 10
        assert positions["MSFT"]["qty"] == 5

    def test_transactions_out_of_order_are_sorted_by_date(self):
        positions = compute_positions(
            [
                _tx("AAPL", "sell", 5, 150.0, date="2026-02-01"),
                _tx("AAPL", "buy", 10, 100.0, date="2026-01-01"),
            ]
        )
        p = positions["AAPL"]
        assert p["qty"] == 5
        assert p["realized_pnl"] == pytest.approx((150 - 100) * 5)

    def test_empty_transactions_returns_empty(self):
        assert compute_positions([]) == {}

    def test_zero_qty_transaction_is_skipped(self):
        positions = compute_positions([_tx("AAPL", "buy", 0, 100.0)])
        assert positions["AAPL"]["qty"] == 0


class TestParseTransactionsCSV:
    def test_parses_valid_csv(self):
        csv_text = "date,symbol,side,qty,price\n2026-01-01,AAPL,buy,10,150.5\n"
        rows = parse_transactions_csv(csv_text)
        assert len(rows) == 1
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["qty"] == 10.0

    def test_parses_optional_fees_and_note(self):
        csv_text = "date,symbol,side,qty,price,fees,note\n2026-01-01,AAPL,buy,10,150.5,4.95,core position\n"
        rows = parse_transactions_csv(csv_text)
        assert rows[0]["fees"] == 4.95
        assert rows[0]["note"] == "core position"

    def test_missing_required_column_raises(self):
        with pytest.raises(ValueError, match="header"):
            parse_transactions_csv("date,symbol,side,qty\n2026-01-01,AAPL,buy,10\n")

    def test_invalid_symbol_raises_with_line_number(self):
        csv_text = "date,symbol,side,qty,price\n2026-01-01,../evil,buy,10,150.5\n"
        with pytest.raises(ValueError, match="line 2"):
            parse_transactions_csv(csv_text)

    def test_invalid_side_raises(self):
        csv_text = "date,symbol,side,qty,price\n2026-01-01,AAPL,hold,10,150.5\n"
        with pytest.raises(ValueError, match="side must be"):
            parse_transactions_csv(csv_text)

    def test_non_numeric_qty_raises(self):
        csv_text = "date,symbol,side,qty,price\n2026-01-01,AAPL,buy,ten,150.5\n"
        with pytest.raises(ValueError, match="non-numeric"):
            parse_transactions_csv(csv_text)

    def test_zero_qty_raises(self):
        csv_text = "date,symbol,side,qty,price\n2026-01-01,AAPL,buy,0,150.5\n"
        with pytest.raises(ValueError, match="positive"):
            parse_transactions_csv(csv_text)

    def test_missing_date_raises(self):
        csv_text = "date,symbol,side,qty,price\n,AAPL,buy,10,150.5\n"
        with pytest.raises(ValueError, match="date is required"):
            parse_transactions_csv(csv_text)

    def test_symbol_normalized_to_uppercase(self):
        csv_text = "date,symbol,side,qty,price\n2026-01-01,aapl,buy,10,150.5\n"
        rows = parse_transactions_csv(csv_text)
        assert rows[0]["symbol"] == "AAPL"


def _price_df(symbols, start="2026-01-01", n=10, base=100.0, step=1.0):
    dates = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame(
        {sym: [base + i * step for i in range(n)] for sym in symbols},
        index=dates,
    )


class TestBuildValueSeries:
    def test_empty_transactions_returns_empty_series(self):
        prices = _price_df(["AAPL"])
        result = build_value_series([], prices)
        assert result.empty

    def test_single_buy_values_at_price_times_qty(self):
        prices = _price_df(["AAPL"], start="2026-01-01", n=5, base=100.0, step=0.0)
        txs = [{"symbol": "AAPL", "side": "buy", "qty": 10, "date": "2026-01-01"}]
        result = build_value_series(txs, prices)
        assert (result == 1000.0).all()

    def test_value_changes_after_additional_buy(self):
        prices = _price_df(["AAPL"], start="2026-01-01", n=5, base=100.0, step=0.0)
        txs = [
            {"symbol": "AAPL", "side": "buy", "qty": 10, "date": "2026-01-01"},
            {"symbol": "AAPL", "side": "buy", "qty": 10, "date": "2026-01-03"},
        ]
        result = build_value_series(txs, prices)
        # dates: 1,2,5,6,7 Jan (business days) -> qty 10 on day1-2, 20 from day3 onward
        assert result.iloc[0] == 1000.0
        assert result.iloc[-1] == 2000.0

    def test_sell_reduces_value_to_zero(self):
        prices = _price_df(["AAPL"], start="2026-01-01", n=5, base=100.0, step=0.0)
        txs = [
            {"symbol": "AAPL", "side": "buy", "qty": 10, "date": "2026-01-01"},
            {"symbol": "AAPL", "side": "sell", "qty": 10, "date": "2026-01-05"},
        ]
        result = build_value_series(txs, prices)
        assert result.iloc[-1] == 0.0

    def test_symbol_missing_from_prices_is_skipped_not_error(self):
        prices = _price_df(["MSFT"], start="2026-01-01", n=5)
        txs = [{"symbol": "AAPL", "side": "buy", "qty": 10, "date": "2026-01-01"}]
        result = build_value_series(txs, prices)
        assert result.empty

    def test_multi_symbol_value_sums_correctly(self):
        prices = _price_df(
            ["AAPL", "MSFT"], start="2026-01-01", n=5, base=100.0, step=0.0
        )
        txs = [
            {"symbol": "AAPL", "side": "buy", "qty": 10, "date": "2026-01-01"},
            {"symbol": "MSFT", "side": "buy", "qty": 5, "date": "2026-01-01"},
        ]
        result = build_value_series(txs, prices)
        assert (result == 1500.0).all()


class TestComputeBenchmarkComparison:
    def test_insufficient_overlap_returns_empty(self):
        pv = pd.Series([100, 101], index=pd.date_range("2026-01-01", periods=2))
        bp = pd.Series([100, 102], index=pd.date_range("2026-01-01", periods=2))
        assert compute_benchmark_comparison(pv, bp) == {}

    def test_identical_series_has_beta_one_and_zero_alpha(self):
        dates = pd.date_range("2026-01-01", periods=30, freq="B")
        values = [100 * (1.001**i) for i in range(30)]
        pv = pd.Series(values, index=dates)
        bp = pd.Series(values, index=dates)
        result = compute_benchmark_comparison(pv, bp, risk_free_rate=0.0)
        assert result["beta"] == pytest.approx(1.0, abs=0.05)
        assert result["alpha_annualized_pct"] == pytest.approx(0.0, abs=1.0)

    def test_indexed_series_start_at_100(self):
        dates = pd.date_range("2026-01-01", periods=10, freq="B")
        pv = pd.Series([200 + i for i in range(10)], index=dates)
        bp = pd.Series([50 + i * 0.5 for i in range(10)], index=dates)
        result = compute_benchmark_comparison(pv, bp)
        assert result["portfolio_indexed"][0]["value"] == 100.0
        assert result["benchmark_indexed"][0]["value"] == 100.0

    def test_outperforming_portfolio_has_positive_alpha(self):
        dates = pd.date_range("2026-01-01", periods=60, freq="B")
        bench_vals = [100 * (1.0005**i) for i in range(60)]
        port_vals = [100 * (1.003**i) for i in range(60)]  # consistently outperforms
        pv = pd.Series(port_vals, index=dates)
        bp = pd.Series(bench_vals, index=dates)
        result = compute_benchmark_comparison(pv, bp, risk_free_rate=0.0)
        assert result["alpha_annualized_pct"] > 0
