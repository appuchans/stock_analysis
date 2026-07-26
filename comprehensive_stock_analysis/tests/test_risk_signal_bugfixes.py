"""Regression tests for the zero-value truthy-check and neutral-signal-count
bugs documented in docs/PHASES.md Phase 2 — fixed alongside the Phase 2
provider work since both live in analysis_tools.py's risk/signal scoring."""

import numpy as np
import pandas as pd
import pytest

from src.stock_analysis.tools.analysis_tools import RiskAnalysisTool, TechnicalAnalysisTool


class TestCreditRiskZeroValueBug:
    """A genuine 0.0 debt_to_equity (no debt at all — the best possible case)
    must score as excellent, and a *missing* debt_to_equity must be excluded
    from the score rather than silently treated as if it were 0.0 (which
    previously rewarded missing data as "no debt")."""

    def _tool(self):
        return RiskAnalysisTool()

    def test_zero_debt_to_equity_scores_as_excellent(self):
        result = self._tool()._analyze_credit_risk({
            "debt_to_equity": 0.0, "interest_coverage": 10.0, "current_ratio": 2.0,
        })
        assert result["debt_to_equity"] == 0.0
        assert result["credit_score"] == 1.0
        assert result["risk_level"] == "Low"

    def test_missing_metric_excluded_not_defaulted_to_zero(self):
        # Only interest_coverage present; debt_to_equity and current_ratio
        # missing entirely (None), not zero.
        result = self._tool()._analyze_credit_risk({"interest_coverage": 10.0})
        assert result["debt_to_equity"] is None
        assert result["current_ratio"] is None
        # Score is normalized over the 1 metric actually evaluated, not
        # silently diluted by two "0" values that were never measured.
        assert result["credit_score"] == 1.0
        assert result["risk_level"] == "Low"

    def test_all_metrics_missing_does_not_divide_by_zero(self):
        result = self._tool()._analyze_credit_risk({})
        assert result["credit_score"] == 0.0
        assert result["risk_level"] == "High"

    def test_liquidity_risk_zero_current_ratio_not_conflated_with_missing(self):
        present = self._tool()._analyze_liquidity_risk({"current_ratio": 0.0})
        missing = self._tool()._analyze_liquidity_risk({})
        assert present["current_ratio"] == 0.0
        assert missing["current_ratio"] is None
        # Both score 0 on this metric (0.0 fails every threshold), but the
        # raw values returned to the caller must not be conflated.
        assert present["current_ratio"] != missing["current_ratio"]

    def test_operational_risk_zero_growth_scores_as_missed_threshold_not_missing(self):
        result = self._tool()._analyze_operational_risk({
            "revenue_growth": 0.0, "earnings_growth": 0.20, "roe": 0.20,
        })
        assert result["revenue_growth"] == 0.0
        # revenue_growth=0.0 fails both thresholds (contributes 0 of 1), the
        # other two hit their top threshold (contribute 1 each) -> 2/3.
        assert result["operational_score"] == pytest.approx(2 / 3)

    def test_operational_risk_all_missing_returns_high_risk_not_crash(self):
        result = self._tool()._analyze_operational_risk({})
        assert result["operational_score"] == 0.0
        assert result["risk_level"] == "High"


class TestNeutralSignalMiscount:
    """neutral_signals must equal the number of indicator groups actually
    evaluated minus buy/sell counts — not a hardcoded 4, which overstates
    neutral_signals whenever an indicator is genuinely unavailable (None)."""

    def _df(self, n=100):
        dates = pd.date_range("2024-01-01", periods=n)
        np.random.seed(7)
        prices = 100 + np.cumsum(np.random.randn(n) * 0.5)
        return pd.DataFrame({
            "open": prices * 0.99, "high": prices * 1.01, "low": prices * 0.98,
            "close": prices, "volume": np.random.randint(1_000_000, 5_000_000, n),
        }, index=dates)

    def test_all_four_groups_present_sums_to_four(self):
        tool = TechnicalAnalysisTool()
        df = self._df()
        indicators = tool._calculate_indicators(df)
        signals = tool._generate_signals(df, indicators)
        total = signals["buy_signals"] + signals["sell_signals"] + signals["neutral_signals"]
        assert total == 4

    def test_missing_indicator_group_excluded_from_total(self):
        tool = TechnicalAnalysisTool()
        df = self._df()
        indicators = dict(tool._calculate_indicators(df))
        # Simulate RSI being genuinely unavailable (not merely in its neutral
        # 30-70 band) — the whole group must drop out of the total, not get
        # silently counted as "neutral".
        indicators["rsi"] = None
        signals = tool._generate_signals(df, indicators)
        total = signals["buy_signals"] + signals["sell_signals"] + signals["neutral_signals"]
        assert total == 3

    def test_two_missing_groups_excluded(self):
        tool = TechnicalAnalysisTool()
        df = self._df()
        indicators = dict(tool._calculate_indicators(df))
        indicators["rsi"] = None
        indicators["macd"] = None
        signals = tool._generate_signals(df, indicators)
        total = signals["buy_signals"] + signals["sell_signals"] + signals["neutral_signals"]
        assert total == 2

    def test_all_indicators_missing_yields_zero_total_not_negative(self):
        tool = TechnicalAnalysisTool()
        df = self._df()
        signals = tool._generate_signals(df, {})
        assert signals["buy_signals"] == 0
        assert signals["sell_signals"] == 0
        assert signals["neutral_signals"] == 0
        assert signals["recommendation"] == "HOLD"
