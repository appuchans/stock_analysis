"""The typeset note's structure — what appears, once, and where."""

import json

import pytest

from src.stock_analysis.tools import pdf_report as P
from src.stock_analysis.tools.report_model import ReportModel


@pytest.fixture
def model(tmp_path, monkeypatch):
    from src.stock_analysis.config.settings import settings

    monkeypatch.setattr(settings, "report_output_dir", str(tmp_path))
    d = tmp_path / "TEST"
    d.mkdir(parents=True)
    (d / "TEST_chart_data.json").write_text(
        json.dumps(
            {
                "asset_type": "stock",
                "company": {"name": "Test Corp", "exchange": "NYQ"},
                "key_stats": {
                    "current_price": 100.0,
                    "low_52w": 80.0,
                    "high_52w": 130.0,
                },
                "snapshot": {
                    "price": 100.0,
                    "price_date": "2026-08-18",
                    "price_basis": "last close",
                },
                "analyst": {
                    "price_targets": {"low": 90.0, "mean": 120.0, "high": 150.0}
                },
                "price_history": [
                    {"date": f"2026-0{i}-01", "close": 90.0 + i} for i in range(1, 9)
                ],
                "benchmark": {
                    "symbol": "S&P 500",
                    "history": [
                        {"date": f"2026-0{i}-01", "close": 100.0 + i}
                        for i in range(1, 9)
                    ],
                },
                "valuation_scenarios": [
                    {
                        "scenario": "Bear",
                        "intrinsic_per_share": 95.0,
                        "growth_pct": 2.0,
                        "discount_pct": 9.0,
                        "terminal_pct": 2.5,
                    },
                    {
                        "scenario": "Base",
                        "intrinsic_per_share": 138.0,
                        "growth_pct": 6.0,
                        "discount_pct": 8.5,
                        "terminal_pct": 2.5,
                    },
                    {
                        "scenario": "Bull",
                        "intrinsic_per_share": 140.0,
                        "growth_pct": 10.0,
                        "discount_pct": 8.0,
                        "terminal_pct": 2.5,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (d / "TEST_investment_recommendation.json").write_text(
        json.dumps(
            {
                "recommendation": "Hold",
                "target_price": 119.9,
                "time_horizon": "12 months",
                "summary": "A summary.",
            }
        ),
        encoding="utf-8",
    )
    (d / "TEST_comprehensive_report.md").write_text(
        "## Investment Thesis\n\nThesis body.\n\n"
        "## Valuation & Recommendation\n\nValuation body.\n",
        encoding="utf-8",
    )
    return ReportModel("TEST")


class TestNoDuplicateExhibits:
    def test_each_chart_appears_exactly_once(self, model, tmp_path):
        """The cover shows the relative chart and _EXHIBIT_FOR also mapped it to
        the thesis section, so it printed on page 1 and again on page 2."""
        work = tmp_path / "charts"
        work.mkdir()
        charts = P._build_exhibits(model, work)
        src = P.build_typst_source(model, charts)
        for name, filename in charts.items():
            assert src.count(f'"{filename}"') == 1, f"{name} rendered more than once"


class TestTargetBridge:
    def test_consensus_echo_is_called_out_in_the_document(self, model):
        """Target 119.9 against a consensus mean of 120.0 and a base case of
        115.0 — an echo the reader is entitled to be told about."""
        assert model.target_bridge_required is True
        src = P.build_typst_source(model, {})
        assert "Target reconciliation" in src

    def test_a_target_that_follows_the_model_says_nothing(self, model):
        model.rec["target_price"] = 137.0
        assert model.target_bridge_required is False
        assert "Target reconciliation" not in P.build_typst_source(model, {})
