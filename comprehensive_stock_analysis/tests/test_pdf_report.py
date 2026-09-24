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


def test_inline_text_strips_html_fragments():
    assert P._inline("<p><strong>IBM</strong> leads &amp; grows.</p>") == (
        "IBM leads & grows."
    )


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


class TestTargetClaimRedaction:
    """A refused target must not survive in the prose.

    The advisor declined to set a target_price, and the cover correctly showed
    no target tile — but the narrative wrote "$325.0 target price" twice,
    lifted from the consensus median printed a page earlier. The prose is
    published unchecked, so a refusal upstream never reached the reader.
    """

    def _model(self, tmp_path, monkeypatch, narrative):
        import json

        from src.stock_analysis.config.settings import settings

        monkeypatch.setattr(settings, "report_output_dir", str(tmp_path))
        d = tmp_path / "TEST"
        d.mkdir(parents=True, exist_ok=True)
        (d / "TEST_chart_data.json").write_text(
            json.dumps({"asset_type": "stock", "key_stats": {"current_price": 100.0}}),
            encoding="utf-8",
        )
        (d / "TEST_investment_recommendation.json").write_text(
            json.dumps({"recommendation": "Buy", "target_price": None}),
            encoding="utf-8",
        )
        (d / "TEST_comprehensive_report.md").write_text(narrative, encoding="utf-8")
        return ReportModel("TEST")

    def test_bold_target_price_is_struck_grammatically(self, tmp_path, monkeypatch):
        m = self._model(
            tmp_path,
            monkeypatch,
            "## Investment Thesis\n\n"
            "We rate Amazon **Buy** with a **$325.0 target price**. More text.\n",
        )
        assert m.prose_asserts_a_target is True
        out = m._readable_narrative()
        assert "$325.0" not in out
        assert "target**" not in out  # no orphaned emphasis marker
        assert "a no published" not in out.lower()  # no orphaned article
        assert "no published price target" in out

    def test_target_price_of_phrasing_is_struck(self, tmp_path, monkeypatch):
        m = self._model(
            tmp_path,
            monkeypatch,
            "## Investment Thesis\n\nBuy, with a target price of $325.0. More.\n",
        )
        out = m._readable_narrative()
        assert "$325.0" not in out
        assert "no published price target" in out

    def test_a_genuinely_reported_consensus_figure_is_left_alone(
        self, tmp_path, monkeypatch
    ):
        """Only a *target* claim is struck — the consensus median is real data."""
        m = self._model(
            tmp_path,
            monkeypatch,
            "## Sentiment\n\nThe consensus target is **326.8373**, with a "
            "median of **325.0** and a range of 230-405.\n",
        )
        out = m._readable_narrative()
        assert "325.0" in out
        assert "326.8373" in out

    def test_a_published_target_is_never_redacted(self, tmp_path, monkeypatch):
        import json

        from src.stock_analysis.config.settings import settings

        monkeypatch.setattr(settings, "report_output_dir", str(tmp_path))
        d = tmp_path / "TEST2"
        d.mkdir(parents=True)
        (d / "TEST2_chart_data.json").write_text(
            json.dumps({"asset_type": "stock", "key_stats": {"current_price": 100.0}}),
            encoding="utf-8",
        )
        (d / "TEST2_investment_recommendation.json").write_text(
            json.dumps({"recommendation": "Hold", "target_price": 116.0}),
            encoding="utf-8",
        )
        (d / "TEST2_comprehensive_report.md").write_text(
            "## Investment Thesis\n\nHold, with a **$116.0 target price**.\n",
            encoding="utf-8",
        )
        m = ReportModel("TEST2")
        assert m.prose_asserts_a_target is False
        assert "$116.0" in m._readable_narrative()


class TestGenerationTimestamp:
    """When the file was produced, distinct from the price's own as-of date."""

    def test_generated_at_appears_and_is_distinct_from_the_price_date(self, model):
        src = P.build_typst_source(model, {}, generated_at="2026-08-20 14:04")
        assert "Generated 2026-08-20 14:04" in src
        # Not the same string as the price label, so a reader cannot confuse
        # "when this file was made" with "what session the price belongs to".
        assert "Generated 2026-08-18" not in src

    def test_defaults_to_now_when_not_supplied(self, model):
        src = P.build_typst_source(model, {})
        assert "Generated " in src


class TestTypstCommentSyntax:
    """Typst comments are "//", not "#" — "#" starts a code expression.

    A Python-style "#"-prefixed explanatory comment was written directly into
    the Typst preamble string, so it compiled as literal source and failed
    with "expected expression" — caught only by the compile-verification test,
    since every other test in this file operates above the string level.
    """

    def test_preamble_contains_no_python_style_comment_lines(self):
        from src.stock_analysis.tools.pdf_report import _PREAMBLE

        for line in _PREAMBLE.split("\n"):
            stripped = line.strip()
            assert not stripped.startswith("# "), (
                f"line starts with a Python-style comment, which Typst parses "
                f"as code: {stripped!r}"
            )
