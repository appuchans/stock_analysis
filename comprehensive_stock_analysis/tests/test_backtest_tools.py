"""Tests for backtest_tools.py — SMA crossover / RSI reversion back-tests."""

import pandas as pd
import pytest

from src.stock_analysis.tools.backtest_tools import BacktestTool


class TestBacktestToolWinRate:
    """win_rate_pct must reflect the compounded return over each contiguous
    holding period ("trade"), not the sign of individual daily returns.

    Regression guard: a prior bug computed win rate off single-day returns,
    which can disagree with the actual trade outcome whenever a trade spans
    more than one day and has mixed up/down days within it.
    """

    def test_win_rate_is_per_trade_not_per_day(self):
        dates = pd.date_range("2024-01-01", periods=8, freq="D")
        # Trade 1 (days 1-3): three consecutive +5% days -> compounds to a
        # clear win (+15.76%).
        # Trade 2 (days 5-6): +5% then -20% -> compounds to a net loss
        # (-16%) even though the first day of the trade was individually
        # positive. A single-day win-rate would have miscounted this trade.
        close = pd.Series(
            [100.0, 105.0, 110.25, 115.7625, 115.7625, 121.550625, 97.2405, 97.2405],
            index=dates,
        )
        signals = pd.Series([0, 1, 1, 1, 0, 1, 1, 0], index=dates)

        tool = BacktestTool()
        result = tool._compute_performance(close, signals, "TEST", "sma_crossover")

        assert result["total_trades"] == 2
        # 1 winning trade out of 2 -> 50%, not the ~66.7% a per-day metric
        # would report (4 up-days out of 6 in-trade days).
        assert result["win_rate_pct"] == pytest.approx(50.0)

    def test_win_rate_all_winning_trades(self):
        dates = pd.date_range("2024-02-01", periods=4, freq="D")
        close = pd.Series([100.0, 105.0, 110.25, 115.7625], index=dates)
        signals = pd.Series([0, 1, 1, 1], index=dates)

        tool = BacktestTool()
        result = tool._compute_performance(close, signals, "TEST", "sma_crossover")

        assert result["win_rate_pct"] == pytest.approx(100.0)

    def test_win_rate_no_trades_is_zero_not_error(self):
        dates = pd.date_range("2024-03-01", periods=4, freq="D")
        close = pd.Series([100.0, 101.0, 99.0, 102.0], index=dates)
        signals = pd.Series([0, 0, 0, 0], index=dates)

        tool = BacktestTool()
        result = tool._compute_performance(close, signals, "TEST", "sma_crossover")

        assert result["total_trades"] == 0
        assert result["win_rate_pct"] == 0.0
