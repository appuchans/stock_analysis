"""Portfolio-level analysis across multiple stocks."""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from crewai.tools import BaseTool


class PortfolioAnalysisTool(BaseTool):
    """Analyses a portfolio: correlation matrix, per-stock metrics, and weight suggestions."""

    name: str = "Portfolio Analysis Tool"
    description: str = (
        "Given a list of stock symbols, calculates the portfolio correlation matrix, "
        "per-stock risk/return metrics, equal-weight allocation, true covariance-based "
        "minimum-variance weights (long-only, fully invested, solved via SLSQP; falls back "
        "to an inverse-variance proxy only if the optimizer fails to converge), "
        "and combined portfolio risk metrics."
    )

    def _run(
        self,
        symbols: List[str],
        period: str = "1y",
        risk_free_rate: float = 0.02,
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        try:
            if len(symbols) < 2:
                return {
                    "error": "At least 2 symbols are required for portfolio analysis"
                }

            raw = yf.download(symbols, period=period, progress=False, auto_adjust=True)[
                "Close"
            ]
            if isinstance(raw, pd.Series):
                raw = raw.to_frame(symbols[0])

            available = [
                s for s in symbols if s in raw.columns and not raw[s].isna().all()
            ]
            if len(available) < 2:
                return {
                    "error": "Insufficient price data returned for the requested symbols"
                }

            prices = raw[available].dropna()
            returns = prices.pct_change().dropna()

            correlation = returns.corr().round(4).to_dict()
            individual = self._individual_metrics(returns, risk_free_rate)
            equal_weights = {s: round(1.0 / len(available), 4) for s in available}
            mv_weights, mv_is_proxy = self._min_variance_weights(returns)
            if weights is not None:
                if set(weights) != set(available):
                    return {
                        "error": "User-supplied weights must match available price-data symbols"
                    }
                portfolio_weights = {
                    symbol: float(weights[symbol]) for symbol in available
                }
                allocation_method = "user_supplied"
            else:
                portfolio_weights = mv_weights
                allocation_method = (
                    "minimum_variance_proxy" if mv_is_proxy else "minimum_variance"
                )
            portfolio_metrics = self._portfolio_metrics(
                returns, portfolio_weights, risk_free_rate
            )

            return {
                "symbols": available,
                "period": period,
                "correlation_matrix": correlation,
                "individual_metrics": individual,
                "equal_weight_allocation": equal_weights,
                "min_variance_weights": mv_weights,
                "portfolio_weights": portfolio_weights,
                "allocation_method": allocation_method,
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

    def _min_variance_weights(self, returns: pd.DataFrame) -> tuple:
        """True covariance-based minimum-variance weights: minimize w^T Σ w
        subject to sum(w) = 1 and w >= 0 (long-only, fully invested), solved
        via SLSQP. Falls back to the inverse-variance proxy (which ignores
        cross-asset covariance entirely) only if the optimizer fails to
        converge — e.g. a near-singular covariance matrix from very few
        return observations.

        Returns (weights, is_proxy).
        """
        cov = returns.cov().values
        n = cov.shape[0]
        try:
            from scipy.optimize import minimize

            def _objective(w: np.ndarray) -> float:
                return float(w @ cov @ w)

            result = minimize(
                _objective,
                x0=np.full(n, 1.0 / n),
                method="SLSQP",
                bounds=[(0.0, 1.0)] * n,
                constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
                options={"maxiter": 500, "ftol": 1e-12},
            )
            if not result.success or not np.isfinite(result.x).all():
                raise RuntimeError(result.message)
            w = np.clip(result.x, 0.0, None)
            total = w.sum()
            if total <= 0:
                raise RuntimeError(
                    "optimizer converged to a degenerate all-zero allocation"
                )
            w = w / total
            return {
                col: round(float(v), 4) for col, v in zip(returns.columns, w)
            }, False
        except Exception:
            return self._min_variance_weights_proxy(returns), True

    def _min_variance_weights_proxy(self, returns: pd.DataFrame) -> Dict[str, float]:
        """Inverse-variance weighting — ignores cross-asset covariance entirely.
        Used only as a fallback when the real optimization fails to converge."""
        var = returns.var().clip(
            lower=1e-8
        )  # floor near-zero variance to avoid inf weights
        inv_var = 1.0 / var
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
