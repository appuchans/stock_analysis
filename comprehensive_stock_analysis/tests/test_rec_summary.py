"""Overview summary derived from an existing report, and its factual guard.

Two failures drove this. A full re-analysis (11 LLM calls, >100k tokens) was
being spent to obtain two sentences the finished recommendation already
contained. And the first generated summary claimed IBM was "near its recent
high" while it sat 28% below it — the prompt had the memo's prose but none of
the price data, so the model filled the gap by inventing.
"""

import json

import pytest

from stock_analysis.web import rec_summary


@pytest.fixture
def report(tmp_path, monkeypatch):
    from stock_analysis.config import settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))

    def _write(symbol="TEST", *, chart=None, rec=None):
        d = tmp_path / symbol
        d.mkdir(parents=True, exist_ok=True)
        if chart is not None:
            (d / f"{symbol}_chart_data.json").write_text(json.dumps(chart))
        if rec is not None:
            (d / f"{symbol}_investment_recommendation.json").write_text(json.dumps(rec))
        return symbol

    return _write


# price 238 in a 199–332 range: 29% up the range, i.e. nowhere near the high.
LOW_IN_RANGE = {
    "key_stats": {"current_price": 238.0, "high_52w": 332.0, "low_52w": 199.0},
    "price_history": [
        {"date": "2025-08-11", "close": 233.0},
        {"date": "2026-02-09", "close": 258.0},
        {"date": "2026-08-10", "close": 238.0},
    ],
    "news": [{"title": "A big AI deal", "publisher": "Reuters"}],
    "catalysts": {"next_earnings_date": "2026-10-21"},
}
REC = {"recommendation": "Hold", "reasoning": "steady cash flows", "key_factors": []}


class TestFactualGuard:
    def test_rejects_near_high_when_far_below(self, report):
        sym = report(chart=LOW_IN_RANGE, rec=REC)
        problem = rec_summary._contradicts_data("It is near its recent high.", sym)
        assert problem and "near its high" in problem

    @pytest.mark.parametrize(
        "claim",
        [
            "trading close to its 52-week high",
            "the stock is at its all-time high",
            "shares sit around their record high",
        ],
    )
    def test_rejects_phrasing_variants(self, report, claim):
        sym = report(chart=LOW_IN_RANGE, rec=REC)
        assert rec_summary._contradicts_data(claim, sym) is not None

    def test_accepts_accurate_statement(self, report):
        sym = report(chart=LOW_IN_RANGE, rec=REC)
        assert (
            rec_summary._contradicts_data("It is 28% below its 52-week high.", sym)
            is None
        )

    def test_rejects_near_low_when_far_above(self, report):
        chart = {
            "key_stats": {"current_price": 320.0, "high_52w": 332.0, "low_52w": 199.0}
        }
        sym = report(chart=chart, rec=REC)
        assert rec_summary._contradicts_data("It trades near its low.", sym) is not None

    def test_near_high_allowed_when_actually_near_high(self, report):
        chart = {
            "key_stats": {"current_price": 330.0, "high_52w": 332.0, "low_52w": 199.0}
        }
        sym = report(chart=chart, rec=REC)
        assert rec_summary._contradicts_data("It is near its high.", sym) is None

    def test_no_price_data_means_no_verdict(self, report):
        """Absent data must not manufacture a contradiction."""
        sym = report(chart={"key_stats": {}}, rec=REC)
        assert rec_summary._contradicts_data("It is near its high.", sym) is None


class TestPerformanceFacts:
    def test_sparse_history_omits_the_change_line(self, report):
        """Three points cannot yield a one-month change — say nothing rather
        than compute a period the data does not cover."""
        sym = report(chart=LOW_IN_RANGE, rec=REC)
        assert "Price change" not in rec_summary._performance_facts(sym)

    def test_includes_real_movement_and_range(self, report):
        chart = dict(
            LOW_IN_RANGE,
            price_history=[
                {"date": f"2025-{(i % 12) + 1:02d}-01", "close": 200.0 + i}
                for i in range(53)
            ],
        )
        sym = report(chart=chart, rec=REC)
        facts = rec_summary._performance_facts(sym)
        assert "Price change" in facts and "1 month" in facts
        assert "52-week high" in facts
        assert "A big AI deal" in facts, "headlines give the model a cause to cite"
        assert "2026-10-21" in facts

    def test_missing_chart_is_empty_not_an_error(self, report):
        assert rec_summary._performance_facts("NOPE") == ""


class TestEnsureSummary:
    def test_returns_existing_without_calling_the_model(self, report, monkeypatch):
        sym = report(chart=LOW_IN_RANGE, rec={**REC, "summary": "Already written."})
        monkeypatch.setattr(
            rec_summary,
            "generate_summary",
            lambda *a, **k: pytest.fail("must not call the LLM"),
        )
        assert rec_summary.ensure_summary(sym) == "Already written."

    def test_force_regenerates(self, report, monkeypatch):
        sym = report(chart=LOW_IN_RANGE, rec={**REC, "summary": "Stale."})
        monkeypatch.setattr(rec_summary, "generate_summary", lambda *a, **k: "Fresh.")
        assert rec_summary.ensure_summary(sym, force=True) == "Fresh."

    def test_persists_so_the_next_load_is_free(self, report, monkeypatch, tmp_path):
        sym = report(chart=LOW_IN_RANGE, rec=REC)
        monkeypatch.setattr(rec_summary, "generate_summary", lambda *a, **k: "Written.")
        rec_summary.ensure_summary(sym)
        saved = json.loads(
            (tmp_path / sym / f"{sym}_investment_recommendation.json").read_text()
        )
        assert saved["summary"] == "Written."

    def test_no_recommendation_returns_none(self, report):
        assert rec_summary.ensure_summary(report(chart=LOW_IN_RANGE)) is None

    def test_generation_failure_leaves_the_file_intact(
        self, report, monkeypatch, tmp_path
    ):
        sym = report(chart=LOW_IN_RANGE, rec=REC)

        def _boom(*a, **k):
            raise RuntimeError("provider down")

        monkeypatch.setattr(rec_summary, "generate_summary", _boom)
        assert rec_summary.ensure_summary(sym) is None
        saved = json.loads(
            (tmp_path / sym / f"{sym}_investment_recommendation.json").read_text()
        )
        assert "summary" not in saved


class TestClean:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ('"Quoted sentence."', "Quoted sentence."),
            ("“Smart quotes.”", "Smart quotes."),
            ("```\nFenced.\n```", "Fenced."),
            ("  Plain.  ", "Plain."),
        ],
    )
    def test_strips_model_wrapping(self, raw, expected):
        assert rec_summary._clean(raw) == expected
