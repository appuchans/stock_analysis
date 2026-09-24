"""Frozen snapshot math, valuation identity, house style, category metering.

Covers the numbers-pipeline hardening: one share count / one market cap per
run (1a), an explicit valuation identity with a reconciled cross-check (1b),
stop-loss gating on a stored basis (1c), per-category token accounting (2),
and stage-output validation (3).
"""

import json

import pytest

from src.stock_analysis import token_meter
from src.stock_analysis.crew.flow_crew import StockAnalysisFlow
from src.stock_analysis.tools.report_model import ReportModel
from src.stock_analysis.web import run_review


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    """Write chart + recommendation artifacts under a tmp reports root."""
    from src.stock_analysis.config import settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))

    def _write(symbol="TEST", *, chart, rec):
        d = tmp_path / symbol
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{symbol}_chart_data.json").write_text(json.dumps(chart))
        (d / f"{symbol}_investment_recommendation.json").write_text(json.dumps(rec))
        return symbol

    return _write


def _chart(**over):
    base = {
        "asset_type": "stock",
        "company": {"name": "Test Corp"},
        "key_stats": {"current_price": 100.0, "market_cap": 10_000_000_000.0},
        "snapshot": {
            "as_of": "2026-09-18T12:00:00",
            "price": 100.0,
            "price_date": "2026-09-17",
            "price_basis": "last close",
            "price_source": "Yahoo Finance",
            "shares_m": 100.0,
            "market_cap": 10_000_000_000.0,
        },
        "valuation_scenarios": [
            {"scenario": "Bear", "intrinsic_per_share": 80.0},
            {"scenario": "Base", "intrinsic_per_share": 120.0},
            {"scenario": "Bull", "intrinsic_per_share": 150.0},
        ],
        "forecast_valuation": {
            "value_per_share": 115.0,
            "method": "m",
            "shares_m": 100.0,
        },
    }
    base.update(over)
    return base


def _rec(**over):
    base = {
        "recommendation": "Buy",
        "target_price": 120.0,
        "time_horizon": "12 months",
        "risk_level": "Medium",
        "confidence": 0.7,
    }
    base.update(over)
    return base


def _codes(result):
    return {i["code"] for i in result["issues"]}


# ── 1a: one share count, one market cap ──────────────────────────────────────


class TestSnapshotMath:
    def test_tile_prefers_snapshot_market_cap(self, artifacts):
        """key_stats carries a stale cap; the tile must use snapshot math."""
        chart = _chart(
            key_stats={"current_price": 100.0, "market_cap": 9_000_000_000.0}
        )
        sym = artifacts(chart=chart, rec=_rec())
        model = ReportModel(sym)
        assert model.market_cap == 10_000_000_000.0
        assert model.shares_m == 100.0

    def test_consistent_run_reviews_clean(self, artifacts):
        sym = artifacts(chart=_chart(), rec=_rec())
        result = run_review.review_run(sym)
        assert "snapshot_price_mismatch" not in _codes(result)
        assert "snapshot_market_cap_inconsistent" not in _codes(result)
        assert "forecast_shares_drifted" not in _codes(result)

    def test_live_quote_cap_is_flagged(self, artifacts):
        """The IBM failure: cap built off the live quote beside settled price."""
        chart = _chart(
            key_stats={"current_price": 100.0, "market_cap": 9_147_000_000.0},
        )
        sym = artifacts(chart=chart, rec=_rec())
        assert "snapshot_market_cap_inconsistent" in _codes(run_review.review_run(sym))

    def test_forecast_share_drift_is_flagged(self, artifacts):
        chart = _chart(
            forecast_valuation={
                "value_per_share": 115.0,
                "method": "m",
                "shares_m": 942.1,
            }
        )
        sym = artifacts(chart=chart, rec=_rec())
        assert "forecast_shares_drifted" in _codes(run_review.review_run(sym))


# ── 1b: valuation identity ───────────────────────────────────────────────────


class TestValuationIdentity:
    def test_identity_line_states_weights(self, artifacts):
        sym = artifacts(chart=_chart(), rec=_rec())
        line = ReportModel(sym).valuation_identity_line
        assert "Target $120.00 = base-case DCF ($120.00, weight 1.0)" in line
        assert "Exit-multiple cross-check $115.00 (-4.2%)" in line

    def test_small_crosscheck_gap_needs_no_bridge(self, artifacts):
        sym = artifacts(chart=_chart(), rec=_rec())
        assert ReportModel(sym).target_bridge_required is False

    def test_large_crosscheck_gap_requires_bridge(self, artifacts):
        chart = _chart(
            forecast_valuation={
                "value_per_share": 90.0,
                "method": "m",
                "shares_m": 100.0,
            }
        )
        sym = artifacts(chart=chart, rec=_rec())
        assert ReportModel(sym).crosscheck_gap_pct == -25.0
        assert ReportModel(sym).target_bridge_required is True
        assert "target_crosscheck_diverges" in _codes(run_review.review_run(sym))


# ── 1c: stop-loss house rule ─────────────────────────────────────────────────


class TestStopLossHouseRule:
    def test_no_basis_no_exhibit(self, artifacts):
        sym = artifacts(chart=_chart(), rec=_rec(stop_loss=85.0))
        assert ReportModel(sym).stop_loss_display is None

    def test_basis_publishes_the_pair(self, artifacts):
        sym = artifacts(
            chart=_chart(), rec=_rec(stop_loss=85.0, stop_loss_basis="bear case")
        )
        assert ReportModel(sym).stop_loss_display == 85.0

    def test_review_flags_basisless_stop(self, artifacts):
        sym = artifacts(chart=_chart(), rec=_rec(stop_loss=85.0))
        assert "stop_loss_without_basis" in _codes(run_review.review_run(sym))


# ── category tier (loader + resolution) ────────────────────────────────────


class TestCategoryTier:
    """The category layer must survive: a past concurrent edit rewrote
    loader/base_agent/llm_config and silently dropped it, which zeroed every
    per-category bucket with no test failing."""

    ELEVEN = {
        "data_collector",
        "technical_analyst",
        "fundamental_analyst",
        "risk_analyst",
        "sentiment_analyst",
        "market_analyst",
        "industry_analyst",
        "competitor_analyst",
        "economic_analyst",
        "investment_advisor",
        "report_generator",
    }

    def test_loader_defaults_cover_all_agents(self):
        from src.stock_analysis.config.loader import LLMConfig

        cfg = LLMConfig()
        assert self.ELEVEN <= set(cfg.agent_categories)
        assert set(cfg.agent_categories.values()) == {
            "extraction",
            "quantitative",
            "narrative",
            "synthesis",
        }

    def test_agent_resolves_its_category(self):
        from src.stock_analysis.agents.base_agent import BaseAgent

        assert (
            BaseAgent("risk_analyst").get_resolved_llm_config()["category"]
            == "quantitative"
        )
        assert (
            BaseAgent("report_generator").get_resolved_llm_config()["category"]
            == "synthesis"
        )

    def test_category_beats_global_loses_to_per_agent(self):
        from src.stock_analysis.agents.base_agent import BaseAgent
        from src.stock_analysis.config.loader import config_loader

        llm_cfg = config_loader.load_llm_config()
        llm_cfg.categories.setdefault("quantitative", {})["model"] = "cat-model"
        try:
            resolved = BaseAgent("risk_analyst").get_resolved_llm_config()
            assert resolved["model"] == "cat-model"
            llm_cfg.agents.setdefault("risk_analyst", {})["model"] = "agent-model"
            assert (
                BaseAgent("risk_analyst").get_resolved_llm_config()["model"]
                == "agent-model"
            )
        finally:
            config_loader.reload_configs()


# ── 2: per-category metering ─────────────────────────────────────────────────


class FakeUsage:
    def __init__(self, total=100, prompt=70, completion=30, cached=0, req=2):
        self.total_tokens = total
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.cached_prompt_tokens = cached
        self.successful_requests = req


class TestCategoryMetering:
    def test_buckets_accumulate_per_category(self):
        token_meter.reset()
        try:
            token_meter.add(FakeUsage(), "extraction")
            token_meter.add(FakeUsage(total=200, req=3), "synthesis")
            snap = token_meter.snapshot()
            assert snap["total_tokens"] == 300
            assert snap["successful_requests"] == 5
            assert snap["by_category"]["extraction"]["total_tokens"] == 100
            assert snap["by_category"]["synthesis"]["successful_requests"] == 3
        finally:
            token_meter.reset()

    def test_uncategorised_calls_count_only_in_total(self):
        token_meter.reset()
        try:
            token_meter.add(FakeUsage())
            snap = token_meter.snapshot()
            assert snap["total_tokens"] == 100
            assert snap["by_category"] == {}
        finally:
            token_meter.reset()


# ── 3: stage validation ──────────────────────────────────────────────────────


class TestStageValidation:
    GOOD = "## Thesis\n\n" + "Analysis body. " * 30 + "\n\n## Risks\n\nMore body. " * 10

    @pytest.fixture
    def flow(self):
        return StockAnalysisFlow()

    def test_accepts_real_analysis(self, flow):
        assert flow._stage_problem("risk", self.GOOD) is None

    def test_rejects_stubs(self, flow):
        assert flow._stage_problem("risk", "") is not None
        assert flow._stage_problem("risk", "## Hi\nshort") is not None

    def test_rejects_sectionless_prose(self, flow):
        assert flow._stage_problem("risk", "Body text. " * 100) is not None

    def test_rejects_leaked_machinery(self, flow):
        bad = self.GOOD + "\nTraceback (most recent call last): boom"
        assert flow._stage_problem("risk", bad) is not None
        bad2 = self.GOOD + "\nError code: 403"
        assert flow._stage_problem("risk", bad2) is not None

    def test_ordinary_prose_is_not_flagged(self, flow):
        text = self.GOOD + "\nThe company failed to meet guidance in Q2. " * 5
        assert flow._stage_problem("risk", text) is None
