"""Portfolio-level analysis across multiple stocks."""

from typing import Any, Dict, List

import numpy as np
import pandas as pd
import yfinance as yf
from crewai.tools import BaseTool


class PortfolioAnalysisTool(BaseTool):
    """Analyses a portfolio: correlation matrix, per-stock metrics, and weight suggestions."""

    name: str = "Portfolio Analysis Tool"
    description: str = (
        "Given a list of stock symbols, calculates the portfolio correlation matrix, "
        "per-stock risk/return metrics, equal-weight allocation, minimum-variance weights, "
        "and combined portfolio risk metrics."
    )

    def _run(
        self,
        symbols: List[str],
        period: str = "1y",
        risk_free_rate: float = 0.02,
    ) -> Dict[str, Any]:
        try:
            if len(symbols) < 2:
                return {"error": "At least 2 symbols are required for portfolio analysis"}

            raw = yf.download(symbols, period=period, progress=False, auto_adjust=True)["Close"]
            if isinstance(raw, pd.Series):
                raw = raw.to_frame(symbols[0])

            available = [s for s in symbols if s in raw.columns and not raw[s].isna().all()]
            if len(available) < 2:
                return {"error": "Insufficient price data returned for the requested symbols"}

            prices = raw[available].dropna()
            returns = prices.pct_change().dropna()

            correlation = returns.corr().round(4).to_dict()
            individual = self._individual_metrics(returns, risk_free_rate)
            equal_weights = {s: round(1.0 / len(available), 4) for s in available}
            mv_weights = self._min_variance_weights(returns)
            portfolio_metrics = self._portfolio_metrics(returns, mv_weights, risk_free_rate)

            return {
                "symbols": available,
                "period": period,
                "correlation_matrix": correlation,
                "individual_metrics": individual,
                "equal_weight_allocation": equal_weights,
                "min_variance_weights": mv_weights,
                "portfolio_metrics": portfolio_metrics,
            }

        except Exception as exc:
            return {"error": f"Portfolio analysis failed: {exc}"}

    def _individual_metrics(self, returns: pd.DataFrame, rfr: float) -> Dict[str, Any]:
        metrics = {}
        for col in returns.columns:
            s = returns[col]
            ann_ret = float(s.mean() * 252)
            ann_vol = float(s.std() * np.sqrt(252))
            sharpe = (ann_ret - rfr) / ann_vol if ann_vol > 0 else 0.0
            cum = (1 + s).cumprod()
            max_dd = float(((cum - cum.cummax()) / cum.cummax()).min())
            var_95 = float(s.quantile(0.05))
            metrics[col] = {
                "annualised_return_pct": round(ann_ret * 100, 2),
                "annualised_volatility_pct": round(ann_vol * 100, 2),
                "sharpe_ratio": round(sharpe, 3),
                "max_drawdown_pct": round(max_dd * 100, 2),
                "var_95_daily_pct": round(var_95 * 100, 2),
            }
        return metrics

    def _min_variance_weights(self, returns: pd.DataFrame) -> Dict[str, float]:
        """Inverse-variance weighting as a simple proxy for minimum-variance allocation."""
        inv_var = 1.0 / returns.var()
        weights = inv_var / inv_var.sum()
        return {k: round(float(v), 4) for k, v in weights.items()}

    def _portfolio_metrics(
        self, returns: pd.DataFrame, weights: Dict[str, float], rfr: float
    ) -> Dict[str, Any]:
        w = pd.Series(weights).reindex(returns.columns).fillna(0)
        port_ret = returns.dot(w)
        ann_ret = float(port_ret.mean() * 252)
        ann_vol = float(port_ret.std() * np.sqrt(252))
        sharpe = (ann_ret - rfr) / ann_vol if ann_vol > 0 else 0.0
        cum = (1 + port_ret).cumprod()
        max_dd = float(((cum - cum.cummax()) / cum.cummax()).min())
        var_95 = float(port_ret.quantile(0.05))
        cvar_95 = float(port_ret[port_ret <= var_95].mean())
        return {
            "annualised_return_pct": round(ann_ret * 100, 2),
            "annualised_volatility_pct": round(ann_vol * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "var_95_daily_pct": round(var_95 * 100, 2),
            "cvar_95_daily_pct": round(cvar_95 * 100, 2),
        }
