"""Post-run display-contract review, and the derived YTD it sits alongside.

Context: an OpenAI structured-output rejection made the recommendation crew
fail on every run, so no <SYM>_investment_recommendation.json was written and
history tiles quietly lost their rating badge, target price and accent border.
Nothing surfaced it. These tests pin the checks that now would.
"""

import json

import pytest

from stock_analysis.web import run_review
from stock_analysis.web.reports_index import _ytd_return


@pytest.fixture
def report(tmp_path, monkeypatch):
    """A symbol whose artifacts live under a tmp reports root."""
    from stock_analysis.config import settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))

    def _write(symbol="TEST", *, html=True, chart=None, rec=None):
        d = tmp_path / symbol
        (d / "html").mkdir(parents=True, exist_ok=True)
        if html:
            (d / "html" / f"{symbol}_report.html").write_text("x" * 5000)
        if chart is not None:
            (d / f"{symbol}_chart_data.json").write_text(json.dumps(chart))
        if rec is not None:
            (d / f"{symbol}_investment_recommendation.json").write_text(json.dumps(rec))
        return symbol

    return _write


GOOD_CHART = {
    "asset_type": "stock",
    "company": {"name": "Test Corp"},
    "key_stats": {"current_price": 100.0},
    "price_history": [{"date": "2025-01-02", "close": 90.0}],
}
GOOD_REC = {
    "recommendation": "BUY",
    "confidence": 0.8,
    "risk_level": "MEDIUM",
    "target_price": 120.0,
}


def _codes(result):
    return {i["code"] for i in result["issues"]}


class TestReviewPasses:
    def test_complete_run_is_clean(self, report):
        sym = report(chart=GOOD_CHART, rec=GOOD_REC)
        result = run_review.review_run(sym)
        assert result["ok"] is True
        assert result["issues"] == []

    def test_numeric_strings_are_accepted(self, report):
        """Older files stored Decimal prices as JSON strings and the gallery
        coerces them with float() — flagging those would be crying wolf."""
        sym = report(chart=GOOD_CHART, rec={**GOOD_REC, "target_price": "58"})
        assert run_review.review_run(sym)["ok"] is True

    def test_absent_target_price_is_allowed(self, report):
        """The advisor may legitimately decline to set a target."""
        sym = report(chart=GOOD_CHART, rec={**GOOD_REC, "target_price": None})
        assert run_review.review_run(sym)["ok"] is True


class TestReviewCatchesRegressions:
    def test_missing_recommendation_is_an_error(self, report):
        """The exact regression that prompted this module."""
        sym = report(chart=GOOD_CHART, rec=None)
        result = run_review.review_run(sym)
        assert result["ok"] is False
        assert "recommendation_missing" in _codes(result)

    def test_prose_target_price_is_an_error(self, report):
        sym = report(
            chart=GOOD_CHART,
            rec={**GOOD_REC, "target_price": "115 (percentage-based target)"},
        )
        result = run_review.review_run(sym)
        assert result["ok"] is False
        assert "target_price_not_numeric" in _codes(result)

    def test_missing_html_is_an_error(self, report):
        sym = report(html=False, chart=GOOD_CHART, rec=GOOD_REC)
        assert "html_missing" in _codes(run_review.review_run(sym))

    def test_stub_html_is_a_warning(self, report, tmp_path):
        sym = report(chart=GOOD_CHART, rec=GOOD_REC)
        (tmp_path / sym / "html" / f"{sym}_report.html").write_text("tiny")
        result = run_review.review_run(sym)
        assert "html_too_small" in _codes(result)
        assert result["ok"] is True, "a stub report is degraded, not fatal"

    def test_missing_chart_data_is_an_error(self, report):
        sym = report(chart=None, rec=GOOD_REC)
        assert "chart_data_missing" in _codes(run_review.review_run(sym))

    def test_non_numeric_current_price_is_an_error(self, report):
        chart = {**GOOD_CHART, "key_stats": {"current_price": "unavailable"}}
        sym = report(chart=chart, rec=GOOD_REC)
        assert "current_price_invalid" in _codes(run_review.review_run(sym))

    def test_empty_price_history_warns_only(self, report):
        chart = {**GOOD_CHART, "price_history": []}
        sym = report(chart=chart, rec=GOOD_REC)
        result = run_review.review_run(sym)
        assert "price_history_empty" in _codes(result)
        assert result["ok"] is True

    def test_out_of_range_confidence_warns(self, report):
        sym = report(chart=GOOD_CHART, rec={**GOOD_REC, "confidence": 87})
        assert "confidence_out_of_range" in _codes(run_review.review_run(sym))

    def test_unknown_recommendation_warns(self, report):
        sym = report(chart=GOOD_CHART, rec={**GOOD_REC, "recommendation": "ACCUMULATE"})
        result = run_review.review_run(sym)
        assert "recommendation_unrecognised" in _codes(result)
        assert result["ok"] is True

    def test_corrupt_json_reads_as_missing(self, report, tmp_path):
        sym = report(chart=GOOD_CHART, rec=GOOD_REC)
        (tmp_path / sym / f"{sym}_investment_recommendation.json").write_text("{oops")
        assert "recommendation_missing" in _codes(run_review.review_run(sym))


class TestYtdReturn:
    def test_uses_last_close_of_prior_year_as_baseline(self):
        history = [
            {"date": "2025-12-31", "close": 100.0},
            {"date": "2026-06-30", "close": 110.0},
            {"date": "2026-08-11", "close": 120.0},
        ]
        assert _ytd_return(history) == pytest.approx(0.20)

    def test_falls_back_to_first_close_of_current_year(self):
        history = [
            {"date": "2026-01-05", "close": 50.0},
            {"date": "2026-08-11", "close": 75.0},
        ]
        assert _ytd_return(history) == pytest.approx(0.50)

    def test_negative_return(self):
        history = [
            {"date": "2025-12-30", "close": 200.0},
            {"date": "2026-08-11", "close": 150.0},
        ]
        assert _ytd_return(history) == pytest.approx(-0.25)

    def test_unsorted_input_is_handled(self):
        history = [
            {"date": "2026-08-11", "close": 120.0},
            {"date": "2025-12-31", "close": 100.0},
        ]
        assert _ytd_return(history) == pytest.approx(0.20)

    @pytest.mark.parametrize(
        "history",
        [
            None,
            [],
            [{"date": "2026-01-02", "close": 10.0}],  # single point
            [{"date": "2026-01-02", "close": 0}, {"date": "2026-08-01", "close": 5}],
            [{"close": 10.0}, {"close": 12.0}],  # no dates
            "not-a-list",
        ],
    )
    def test_unusable_input_returns_none(self, history):
        assert _ytd_return(history) is None

    def test_ignores_malformed_points(self):
        history = [
            {"date": "2025-12-31", "close": 100.0},
            "junk",
            {"date": "bad-date", "close": 5.0},
            {"date": "2026-08-11", "close": 110.0},
        ]
        assert _ytd_return(history) == pytest.approx(0.10)


class TestRecommendationSchemaIsOpenAiSafe:
    def test_no_lookaround_in_json_schema(self):
        """CrewAI hands this model to OpenAI as a structured-output schema, and
        OpenAI rejects regex lookaround. Decimal fields reintroduce it — this is
        the guard against that regression."""
        from stock_analysis.models.stock_data import InvestmentRecommendation

        schema = json.dumps(InvestmentRecommendation.model_json_schema())
        assert (
            "(?=" not in schema and "(?!" not in schema
        ), "lookaround in the schema will 400 the recommendation crew"


class TestDegradationsAreSurfaced:
    """A stage can fail, be worked around, and leave a *stale* artifact from an
    earlier run on disk — so the file checks alone would call it healthy. The
    flow's own degradation list is what closes that gap."""

    def test_degradations_become_issues(self, report):
        sym = report(chart=GOOD_CHART, rec=GOOD_REC)
        result = run_review.review_run(
            sym, degradations=["recommendation: 400 invalid schema"]
        )
        assert "stage_degraded" in _codes(result)
        assert result["warning_count"] == 1

    def test_degradations_do_not_fail_an_otherwise_good_run(self, report):
        """Degraded but displayable — the report is still worth opening."""
        sym = report(chart=GOOD_CHART, rec=GOOD_REC)
        result = run_review.review_run(sym, degradations=["html render: boom"])
        assert result["ok"] is True

    def test_no_degradations_is_clean(self, report):
        sym = report(chart=GOOD_CHART, rec=GOOD_REC)
        assert run_review.review_run(sym, degradations=[])["issues"] == []

    def test_stale_artifact_plus_degradation_is_still_flagged(self, report):
        """The exact blind spot: a failed recommendation stage leaves last
        run's JSON in place, so every file check passes."""
        sym = report(chart=GOOD_CHART, rec=GOOD_REC)
        assert run_review.review_run(sym)["issues"] == [], "file checks see nothing"
        flagged = run_review.review_run(sym, degradations=["recommendation: 400"])
        assert "stage_degraded" in _codes(flagged)


class TestFlowRecordsDegradations:
    def test_state_has_a_degradations_list(self):
        from stock_analysis.crew.flow_crew import StockAnalysisState

        assert StockAnalysisState().degradations == []

    def test_degradations_do_not_change_run_status(self):
        """Degrade-don't-fail is deliberate; visibility is the fix, not failing."""
        from stock_analysis.crew.flow_crew import StockAnalysisState

        state = StockAnalysisState()
        state.degradations.append("recommendation: boom")
        assert state.errors == [], "a degradation must not become a run error"
