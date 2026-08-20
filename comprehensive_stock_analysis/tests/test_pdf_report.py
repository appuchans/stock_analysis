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


class TestTheDocumentActuallyCompiles:
    """A render failure returns None, which is easy to miss and easy to ship.

    An unescaped dollar sign in "Value from this forecast: $371.92" opened
    Typst math mode; the next dollar in the method string beside it closed a
    delimiter that was never meant to be open, and the whole compile failed.
    The report silently became None while every other test stayed green.
    """

    def test_a_full_document_compiles(self, model, tmp_path):
        import typst

        work = tmp_path / "typst"
        work.mkdir()
        charts = P._build_exhibits(model, work)
        (work / "r.typ").write_text(
            P.build_typst_source(model, charts), encoding="utf-8"
        )
        typst.compile(str(work / "r.typ"), output=str(work / "r.pdf"))
        assert (work / "r.pdf").stat().st_size > 1000

    def test_a_forecast_with_currency_compiles(self, model, tmp_path):
        """Currency in the forecast block is what broke it."""
        import typst

        model.chart["forecast"] = {
            "years": [
                {
                    "year": 2026,
                    "revenue_m": 828157.2,
                    "revenue_growth_pct": 15.5,
                    "operating_margin_pct": 12.3,
                    "operating_income_m": 102163.0,
                    "capex_pct_of_revenue": 17.6,
                    "free_cash_flow_m": 15600.0,
                },
            ],
            "assumptions": {
                "revenue_basis": "consensus",
                "base_operating_margin_pct": 11.2,
                "margin_change_ppt_per_year": 1.19,
                "operating_cf_margin_pct": 19.5,
                "capex_pct_now": 18.4,
                "capex_pct_reverting_to": 13.5,
            },
        }
        model.chart["forecast_valuation"] = {
            "value_per_share": 371.92,
            "method": "2028 operating income of $154.2bn at 35.8x EV/EBIT",
        }
        work = tmp_path / "typst2"
        work.mkdir()
        (work / "r.typ").write_text(P.build_typst_source(model, {}), encoding="utf-8")
        typst.compile(str(work / "r.typ"), output=str(work / "r.pdf"))
        assert (work / "r.pdf").exists()
