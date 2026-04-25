"""Backtesting tools for evaluating trading strategies on historical price data."""

from typing import Any, Dict

import numpy as np
import pandas as pd
import yfinance as yf
from crewai_tools import BaseTool


class BacktestTool(BaseTool):
    """Backtests moving-average crossover and RSI mean-reversion strategies."""

    name: str = "Backtest Tool"
    description: str = (
        "Backtests a trading strategy (sma_crossover or rsi_reversion) against "
        "historical data and returns annualised performance metrics."
    )

    def _run(
        self,
        symbol: str,
        strategy: str = "sma_crossover",
        period: str = "2y",
        fast_window: int = 20,
        slow_window: int = 50,
        rsi_window: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
    ) -> Dict[str, Any]:
        try:
            hist = yf.download(symbol, period=period, progress=False, auto_adjust=True)
            if hist.empty:
                return {"error": f"No historical data for {symbol}"}

            close = hist["Close"].squeeze()

            if strategy == "sma_crossover":
                signals = self._sma_crossover_signals(close, fast_window, slow_window)
            elif strategy == "rsi_reversion":
                signals = self._rsi_reversion_signals(close, rsi_window, rsi_oversold, rsi_overbought)
            else:
                return {"error": f"Unknown strategy '{strategy}'. Use sma_crossover or rsi_reversion."}

            return self._compute_performance(close, signals, symbol, strategy)

        except Exception as exc:
            return {"error": f"Backtest failed: {exc}"}

    # ------------------------------------------------------------------
    # Signal generators
    # ------------------------------------------------------------------

    def _sma_crossover_signals(self, close: pd.Series, fast: int, slow: int) -> pd.Series:
        fast_ma = close.rolling(fast).mean()
        slow_ma = close.rolling(slow).mean()
        # Shift by 1 so we trade at the next day's open
        return (fast_ma > slow_ma).astype(float).shift(1).fillna(0)

    def _rsi_reversion_signals(
        self, close: pd.Series, window: int, oversold: float, overbought: float
    ) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        pos = pd.Series(np.nan, index=close.index)
        pos[rsi < oversold] = 1.0
        pos[rsi > overbought] = 0.0
        return pos.ffill().fillna(0).shift(1).fillna(0)

    # ------------------------------------------------------------------
    # Performance metrics
    # ------------------------------------------------------------------

    def _compute_performance(
        self, close: pd.Series, signals: pd.Series, symbol: str, strategy: str
    ) -> Dict[str, Any]:
        daily_returns = close.pct_change()
        strategy_returns = (signals * daily_returns).dropna()

        bh_total = float((close.iloc[-1] / close.iloc[0]) - 1)

        cum = (1 + strategy_returns).cumprod()
        strat_total = float(cum.iloc[-1]) - 1

        mean_ret = float(strategy_returns.mean())
        std_ret = float(strategy_returns.std())
        sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0

        rolling_max = cum.cummax()
        max_drawdown = float(((cum - rolling_max) / rolling_max).min())

        signal_changes = signals.diff().abs()
        trade_mask = signal_changes.shift(-1) > 0
        win_rate = float((strategy_returns[trade_mask] > 0).mean()) if trade_mask.any() else 0.0
        total_trades = int(signal_changes.sum() / 2)

        return {
            "symbol": symbol,
            "strategy": strategy,
            "period": f"{close.index[0].date()} to {close.index[-1].date()}",
            "total_return_pct": round(strat_total * 100, 2),
            "buy_and_hold_return_pct": round(bh_total * 100, 2),
            "annualised_sharpe": round(sharpe, 3),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "win_rate_pct": round(win_rate * 100, 2),
            "total_trades": total_trades,
            "outperforms_buy_and_hold": strat_total > bh_total,
        }
