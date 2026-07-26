"""Tests for tools/portfolio_tools.py's PortfolioAnalysisTool, focused on the
Phase 4c upgrade from an inverse-variance proxy to true covariance-based
minimum-variance optimization (and its documented fallback)."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.stock_analysis.tools.portfolio_tools import PortfolioAnalysisTool


def _price_frame(symbols, n=252, seed=7, corr=0.0):
    """Synthetic daily close prices with a controllable pairwise correlation
    (for 2 symbols) so optimizer behavior can be asserted meaningfully."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    if len(symbols) == 2 and corr:
        cov = [[1.0, corr], [corr, 1.0]]
        shocks = rng.multivariate_normal([0, 0], cov, size=n) * 0.01
    else:
        shocks = rng.normal(0, 0.01, size=(n, len(symbols)))
    prices = {}
    for i, sym in enumerate(symbols):
        prices[sym] = 100 * np.cumprod(1 + shocks[:, i])
    return pd.DataFrame(prices, index=dates)


class TestMinVarianceOptimizer:
    def test_weights_sum_to_one_and_are_non_negative(self):
        tool = PortfolioAnalysisTool()
        prices = _price_frame(["A", "B", "C"])
        returns = prices.pct_change().dropna()
        weights, is_proxy = tool._min_variance_weights(returns)
        assert is_proxy is False
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)
        assert all(w >= -1e-6 for w in weights.values())

    def test_low_variance_asset_gets_more_weight(self):
        tool = PortfolioAnalysisTool()
        rng = np.random.default_rng(3)
        dates = pd.date_range("2025-01-01", periods=252, freq="B")
        low_vol = 100 * np.cumprod(1 + rng.normal(0, 0.002, 252))
        high_vol = 100 * np.cumprod(1 + rng.normal(0, 0.04, 252))
        prices = pd.DataFrame({"LOW": low_vol, "HIGH": high_vol}, index=dates)
        returns = prices.pct_change().dropna()
        weights, _ = tool._min_variance_weights(returns)
        assert weights["LOW"] > weights["HIGH"]

    def test_negatively_correlated_assets_reduce_portfolio_variance(self):
        """The whole point of true covariance optimization vs the old
        inverse-variance proxy: it should exploit negative correlation to
        build a lower-variance portfolio than equal weight, even when both
        assets have identical individual variance (a case the proxy can't
        distinguish from zero correlation)."""
        tool = PortfolioAnalysisTool()
        prices = _price_frame(["A", "B"], corr=-0.8)
        returns = prices.pct_change().dropna()
        weights, is_proxy = tool._min_variance_weights(returns)
        assert is_proxy is False

        w = pd.Series(weights)
        cov = returns.cov()
        opt_var = float(w @ cov @ w)
        equal_w = pd.Series({"A": 0.5, "B": 0.5})
        equal_var = float(equal_w @ cov @ equal_w)
        assert opt_var < equal_var

    def test_falls_back_to_proxy_when_optimizer_fails(self):
        class _FailedResult:
            success = False
            message = "did not converge"
            x = np.array([np.nan, np.nan])

        # _min_variance_weights does `from scipy.optimize import minimize`
        # locally, so patching the source module is what actually takes effect.
        with patch("scipy.optimize.minimize", return_value=_FailedResult()):
            tool = PortfolioAnalysisTool()
            prices = _price_frame(["A", "B"])
            returns = prices.pct_change().dropna()
            weights, is_proxy = tool._min_variance_weights(returns)
        assert is_proxy is True
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


class TestRunAllocationMethodLabel:
    def _mock_download(self, symbols):
        prices = _price_frame(symbols)
        return prices

    def test_run_labels_true_optimization(self):
        tool = PortfolioAnalysisTool()
        with patch("yfinance.download") as mock_dl:
            mock_dl.return_value = pd.concat(
                {"Close": self._mock_download(["A", "B"])}, axis=1
            )
            result = tool._run(["A", "B"])
        assert result["allocation_method"] == "minimum_variance"
        assert result["portfolio_weights"] == result["min_variance_weights"]

    def test_run_user_supplied_weights_bypass_optimizer(self):
        tool = PortfolioAnalysisTool()
        with patch("yfinance.download") as mock_dl:
            mock_dl.return_value = pd.concat(
                {"Close": self._mock_download(["A", "B"])}, axis=1
            )
            result = tool._run(["A", "B"], weights={"A": 0.7, "B": 0.3})
        assert result["allocation_method"] == "user_supplied"
        assert result["portfolio_weights"] == {"A": 0.7, "B": 0.3}
