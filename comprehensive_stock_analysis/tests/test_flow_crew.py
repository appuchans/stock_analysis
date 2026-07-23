"""Tests for StockAnalysisFlow's per-run state handling in flow_crew.py."""

import pytest

from src.stock_analysis.crew import flow_crew
from src.stock_analysis.crew.flow_crew import StockAnalysisFlow


class TestAnalyzeStockStateReset:
    """analyze_stock() must clear every per-stage state field at the start of
    each call, so a `StockAnalysisFlow` instance re-used across symbols (e.g.
    a batch run) never leaks a prior symbol's results into the next one.

    Regression guard for a cross-symbol state leak: stage fields such as
    `ownership`/`technical`/`recommendation` are plain mutable dicts on the
    shared `StockAnalysisState`, so without an explicit reset a stale value
    from symbol A would still be present when symbol B's stages read/write it.
    """

    def _make_flow(self) -> StockAnalysisFlow:
        # asset_type="stock" (not "auto") so _resolve_asset_type never calls
        # the real _detect_asset_type()/yfinance network path.
        return StockAnalysisFlow(use_data_cache=False, asset_type="stock")

    def _poison_state(self, flow: StockAnalysisFlow) -> None:
        """Simulate leftover results from a previous symbol's run."""
        flow.state.symbol = "OLDSYM"
        flow.state.errors = ["stale error from OLDSYM"]
        flow.state.report = "stale report from OLDSYM"
        flow.state.recommendation = {"result": "stale recommendation from OLDSYM"}
        flow.state.technical = {"result": "stale data from a previous symbol"}
        flow.state.fundamental = {"result": "stale data from a previous symbol"}
        flow.state.ownership = {"result": "stale data from a previous symbol"}
        flow.state.risk = {"result": "stale data from a previous symbol"}
        flow.state.sentiment = {"result": "stale data from a previous symbol"}
        flow.state.market = {"result": "stale data from a previous symbol"}
        flow.state.industry = {"result": "stale data from a previous symbol"}
        flow.state.competitor = {"result": "stale data from a previous symbol"}
        flow.state.economic = {"result": "stale data from a previous symbol"}

    def test_state_is_reset_before_kickoff_runs(self, monkeypatch):
        flow = self._make_flow()
        self._poison_state(flow)

        captured = {}

        def _fake_kickoff(inputs=None, **kwargs):
            # Snapshot state exactly as analyze_stock() hands off to the real
            # Flow machinery — this is what the first stage would actually see.
            captured["errors"] = list(flow.state.errors)
            captured["report"] = flow.state.report
            captured["recommendation"] = dict(flow.state.recommendation)
            captured["technical"] = dict(flow.state.technical)
            captured["fundamental"] = dict(flow.state.fundamental)
            captured["ownership"] = dict(flow.state.ownership)
            captured["risk"] = dict(flow.state.risk)
            captured["sentiment"] = dict(flow.state.sentiment)
            captured["market"] = dict(flow.state.market)
            captured["industry"] = dict(flow.state.industry)
            captured["competitor"] = dict(flow.state.competitor)
            captured["economic"] = dict(flow.state.economic)
            return None

        monkeypatch.setattr(flow, "kickoff", _fake_kickoff)

        result = flow.analyze_stock("NEWSYM")

        assert captured["errors"] == []
        assert captured["report"] == ""
        assert captured["recommendation"] == {}
        assert captured["technical"] == {}
        assert captured["fundamental"] == {}
        assert captured["ownership"] == {}
        assert captured["risk"] == {}
        assert captured["sentiment"] == {}
        assert captured["market"] == {}
        assert captured["industry"] == {}
        assert captured["competitor"] == {}
        assert captured["economic"] == {}
        assert result["status"] == "completed"

    def test_second_analyze_call_does_not_see_first_calls_results(self, monkeypatch):
        """End-to-end version: run analyze_stock twice on the same instance
        and confirm the second run's reported state has no trace of the first."""
        flow = self._make_flow()

        def _kickoff_writes_ownership(inputs=None, **kwargs):
            # Real CrewAI Flow.kickoff merges `inputs` into state before running
            # stages; this fake mimics that for `symbol` since we bypass the
            # real Flow machinery entirely.
            flow.state.symbol = inputs["symbol"]
            flow.state.ownership = {"result": f"ownership data for {flow.state.symbol}"}
            return None

        monkeypatch.setattr(flow, "kickoff", _kickoff_writes_ownership)

        first = flow.analyze_stock("AAPL")
        assert flow.state.ownership == {"result": "ownership data for AAPL"}

        second = flow.analyze_stock("MSFT")
        # The reset happens before kickoff runs again, and this fake kickoff
        # immediately repopulates ownership for the *new* symbol only.
        assert flow.state.ownership == {"result": "ownership data for MSFT"}
        assert first["symbol"] == "AAPL"
        assert second["symbol"] == "MSFT"

    def test_stage_errors_mark_the_result_as_failed(self, monkeypatch):
        flow = self._make_flow()

        def _kickoff_with_stage_error(inputs=None, **kwargs):
            flow.state.errors.append("risk: LLM provider unavailable")

        monkeypatch.setattr(flow, "kickoff", _kickoff_with_stage_error)

        result = flow.analyze_stock("AAPL")

        assert result["status"] == "failed"
        assert result["error"] == "risk: LLM provider unavailable"
        assert result["errors"] == ["risk: LLM provider unavailable"]

    def test_invalid_symbol_fails_before_kickoff(self, monkeypatch):
        flow = self._make_flow()
        monkeypatch.setattr(flow, "kickoff", pytest.fail)

        result = flow.analyze_stock("../outside")

        assert result["status"] == "failed"
        assert "symbol must be" in result["error"]


class TestSynthesizeRecommendationFailure:
    """A recommendation-crew failure must degrade gracefully (matching
    generate_report's behavior) instead of propagating and aborting the whole
    flow with zero artifact — see CLAUDE.md's LLM Initialisation section."""

    def _make_flow(self) -> StockAnalysisFlow:
        flow = StockAnalysisFlow(use_data_cache=False, asset_type="stock")
        flow.state.symbol = "AAPL"
        flow.state.technical = {"result": "some technical analysis"}
        return flow

    def test_crew_exception_does_not_propagate(self, monkeypatch):
        flow = self._make_flow()

        def _raise(*args, **kwargs):
            raise RuntimeError("LLM provider unavailable")

        monkeypatch.setattr(flow_crew, "_run_crew", _raise)

        flow.synthesize_recommendation()  # must not raise

        assert flow.state.recommendation == {}

    def test_crew_exception_skips_writing_report_file(self, monkeypatch):
        flow = self._make_flow()
        monkeypatch.setattr(
            flow_crew,
            "_run_crew",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        written = []
        monkeypatch.setattr(
            flow_crew, "_write_report_file", lambda *a, **k: written.append(a)
        )

        flow.synthesize_recommendation()

        assert written == []


class TestChartDataFreshnessTimestamp:
    """chart_data.json carries a `data_fetched_at` timestamp so the web UI can
    show how stale the underlying data is. It must be stamped once at the real
    network fetch (inside the cached bundle) — not re-stamped on every apply —
    so a 24h-cached bundle still reports its true (older) fetch time instead of
    looking freshly pulled."""

    def _make_flow(self) -> StockAnalysisFlow:
        flow = StockAnalysisFlow(use_data_cache=False, asset_type="stock")
        flow.state.symbol = "AAPL"
        return flow

    def test_apply_structured_bundle_propagates_fetch_timestamp_into_chart(self, monkeypatch):
        flow = self._make_flow()
        written = []
        monkeypatch.setattr(
            flow_crew, "_write_report_file",
            lambda symbol, filename, content: written.append((symbol, filename, content)),
        )
        # sentiment_history recomputation touches disk; keep it inert for this test.
        monkeypatch.setattr(flow, "_update_sentiment_history", lambda snapshot: [])

        bundle = {
            "structured": {}, "technical_summary": None,
            "chart": {"asset_type": "stock", "company": {"name": "Apple"}},
            "data_fetched_at": "2026-07-20T10:00:00",
        }
        flow._apply_structured_bundle(bundle)

        assert len(written) == 1
        _symbol, filename, content = written[0]
        assert filename == "AAPL_chart_data.json"
        import json as _json
        chart = _json.loads(content)
        assert chart["data_fetched_at"] == "2026-07-20T10:00:00"

    def test_apply_structured_bundle_handles_missing_timestamp(self, monkeypatch):
        """Older cached bundles (pre-dating this field) must not crash — the
        chip is simply omitted by the frontend when the value is falsy."""
        flow = self._make_flow()
        written = []
        monkeypatch.setattr(
            flow_crew, "_write_report_file",
            lambda symbol, filename, content: written.append((symbol, filename, content)),
        )
        monkeypatch.setattr(flow, "_update_sentiment_history", lambda snapshot: [])

        bundle = {"structured": {}, "technical_summary": None, "chart": {"asset_type": "stock"}}
        flow._apply_structured_bundle(bundle)

        import json as _json
        chart = _json.loads(written[0][2])
        assert chart["data_fetched_at"] is None
