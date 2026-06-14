"""Tests for the HTML report rendering pipeline."""

import json

import pytest

from src.stock_analysis.tools import report_tools
from src.stock_analysis.tools.report_tools import render_html_report

_CHART_DATA = {
    "company": {
        "name": "Test Corporation",
        "website": "https://www.testcorp.com",
        "sector": "Technology",
        "industry": "Software",
        "exchange": "NMS",
    },
    "price_history": [
        {"date": "2025-07-01", "close": 100.0},
        {"date": "2025-10-01", "close": 120.0},
        {"date": "2026-01-01", "close": 110.0},
        {"date": "2026-04-01", "close": 130.0},
    ],
    "quarterly_revenue_m": {
        "2025-09-30": 1000.0,
        "2025-12-31": 1200.0,
        "2026-03-31": 1500.0,
    },
    "key_stats": {
        "current_price": 130.0,
        "market_cap": 3_200_000_000_000,
        "pe_ratio": 31.4,
        "high_52w": 150.0,
        "low_52w": 90.0,
        "beta": 1.8,
    },
    "analyst": {
        "price_targets": {"current_price": 130.0, "low": 100.0, "mean": 160.0,
                          "median": 158.0, "high": 220.0},
        "rating_counts": {"period": "0m", "strong_buy": 10, "buy": 40,
                          "hold": 5, "sell": 1, "strong_sell": 0},
    },
    "sentiment_snapshot": {
        "stocktwits_bullish_pct": 86.7,
        "stocktwits_labeled": 15,
        "watchers": 650000,
        "put_call_oi_ratio": 0.51,
        "short_pct_of_float": 1.22,
        "fear_greed_score": 33.7,
        "fear_greed_rating": "fear",
        "search_momentum_pct": -18.7,
    },
    "catalysts": {
        "next_earnings_date": "2026-08-26",
        "earnings_eps_estimate": 2.08,
        "ex_dividend_date": "2026-06-03",
    },
    "peers": [
        {"symbol": "TEST", "name": "Test Corporation", "market_cap_b": 3200.0,
         "pe_ttm": 31.4, "fwd_pe": 25.1, "revenue_growth_pct": 65.5,
         "operating_margin_pct": 60.4, "is_subject": True},
        {"symbol": "PEER", "name": "Peer Inc", "market_cap_b": 900.0,
         "pe_ttm": 40.2, "fwd_pe": 30.5, "revenue_growth_pct": 20.0,
         "operating_margin_pct": 25.0, "is_subject": False},
    ],
    "valuation_scenarios": [
        {"scenario": "Bear", "growth_pct": 12.0, "discount_pct": 12.0,
         "terminal_pct": 2.5, "intrinsic_per_share": 123.55},
        {"scenario": "Base", "growth_pct": 24.0, "discount_pct": 10.0,
         "terminal_pct": 2.5, "intrinsic_per_share": 209.73},
    ],
    "sentiment_history": [
        {"date": "2026-06-01", "stocktwits_bullish_pct": 62.0},
        {"date": "2026-06-08", "stocktwits_bullish_pct": 75.0},
        {"date": "2026-06-12", "stocktwits_bullish_pct": 86.7},
    ],
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """The live chart-data fallback must never hit the network in tests."""
    import yfinance as yf

    def _boom(*a, **k):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(yf, "Ticker", _boom)


@pytest.fixture
def report_dir(tmp_path, monkeypatch):
    """Point the report output dir at a tmp dir pre-populated with specialist files."""
    monkeypatch.setattr(report_tools.settings, "report_output_dir", str(tmp_path))
    sym_dir = tmp_path / "TEST"
    sym_dir.mkdir()
    (sym_dir / "TEST_fundamental_analysis.md").write_text(
        "# Fundamental Analysis\n\nRevenue grew 12% YoY in FY2025.\n\n- Strong margins\n"
        "\n## Data Sources & Gaps\n\n- Source: Yahoo Finance statements (2026-06-12)\n"
        "- Gap: segment revenue not available\n",
        encoding="utf-8",
    )
    (sym_dir / "TEST_risk_analysis.md").write_text(
        "# Risk Analysis\n\nKey risk is customer concentration.\n", encoding="utf-8"
    )
    (sym_dir / "TEST_comprehensive_report.md").write_text(
        "## Investment Thesis\n\nBuy with a $160 target on three pillars.\n\n"
        "## Business Overview\n\nTestCorp sells widgets to enterprises worldwide.\n\n"
        "## Financial Performance\n\nRevenue is growing steadily.\n\n"
        "## Sentiment & Positioning\n\nStreet is constructive.\n\n"
        "## Valuation & Recommendation\n\nWe rate TestCorp a BUY.\n",
        encoding="utf-8",
    )
    (sym_dir / "TEST_investment_recommendation.md").write_text(
        "## Recommendation: BUY\n\nTarget Price: $123.45\n\nSolid growth story.\n",
        encoding="utf-8",
    )
    (sym_dir / "TEST_chart_data.json").write_text(
        json.dumps(_CHART_DATA), encoding="utf-8"
    )
    return tmp_path


class TestRenderHtmlReport:
    """render_html_report must produce HTML deterministically, without an LLM."""

    def test_renders_html_from_files_on_disk(self, report_dir):
        result = render_html_report("TEST")
        assert result.get("status") == "success"
        assert result.get("format") == "html"
        html_files = list((report_dir / "TEST" / "html").glob("*.html"))
        assert len(html_files) == 1
        content = html_files[0].read_text(encoding="utf-8")
        # Recommendation extracted from the markdown fallback
        assert "BUY" in content
        # Specialist sections embedded
        assert "Revenue grew 12% YoY" in content
        assert "customer concentration" in content

    def test_narrative_is_body_and_specialists_are_appendices(self, report_dir):
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        # Synthesized narrative is the main body
        assert 'id="analysis"' in html
        assert "TestCorp sells widgets" in html
        # Specialist reports demoted to collapsible appendices
        assert html.count("<details") >= 2
        assert "Appendix 1:" in html
        # No auto-built executive summary when the narrative exists
        assert 'id="executive-summary"' not in html

    def test_gaps_consolidated_into_single_appendix(self, report_dir):
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        assert 'id="data-sources-gaps"' in html
        assert "segment revenue not available" in html
        # The gap text must not also remain inside the fundamental appendix body
        fundamental_appendix = html.split('id="detail-fundamental_analysis"')[1].split("</details>")[0]
        assert "segment revenue not available" not in fundamental_appendix

    def test_key_stats_and_analyst_visuals_render(self, report_dir):
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        assert "Market Cap" in html and "$3.2T" in html
        assert "52-Week Range" in html
        assert 'id="analyst-consensus"' in html
        assert "Analyst Price Targets" in html
        assert "Analyst Ratings" in html and "56 analysts" in html
        assert "86.7% bullish of 15 labeled" in html
        assert "0.51 (bullish tilt)" in html

    def test_investor_features_render(self, report_dir):
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        # Catalysts strip
        assert "Next Earnings" in html and "2026-08-26" in html
        assert "est. EPS $2.08" in html
        # Peer comparison table with subject row highlighted
        assert 'id="peer-comparison"' in html
        assert "PEER — Peer Inc" in html
        assert "font-weight:700" in html
        # Valuation scenario grid with upside vs current price (130)
        assert 'id="valuation-scenarios"' in html
        assert "$209.73" in html and "+61.3%" in html
        # Sentiment trend: chart + delta chip + search interest chip
        assert "Retail Bullishness Over Time" in html
        assert "86.7% bullish (was 75% on 06-08)" in html
        assert "-18.7% vs 3-mo avg" in html
        # Short interest + market mood chips
        assert "1.22% of float" in html
        assert "33.7" in html
        # Regression: the Fear & Greed label must never clobber the
        # recommendation badge (rating variable shadowing)
        assert 'class="badge buy">BUY' in html
        assert ">fear<" not in html.split('class="badge')[1][:60]

    def test_visuals_interleave_into_matching_sections(self, report_dir):
        """Charts/tables must appear INSIDE their narrative sections — the report
        is one argument, not a dashboard followed by an essay."""
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        # Match the section h2 ids (the TOC links contain the anchors too)
        thesis_pos = html.index('id="sec-investment-thesis"')
        business_pos = html.index('id="sec-business-overview"')
        financial_pos = html.index('id="sec-financial-performance"')
        sentiment_pos = html.index('id="sec-sentiment-positioning"')
        valuation_pos = html.index('id="sec-valuation-recommendation"')
        # Price chart lives inside the Investment Thesis section
        assert thesis_pos < html.index('id="price-chart"') < business_pos
        # Peer table inside Business Overview
        assert business_pos < html.index('id="peer-comparison"') < financial_pos
        # Revenue chart inside Financial Performance
        assert financial_pos < html.index('id="revenue-chart"') < sentiment_pos
        # Consensus visuals inside Sentiment; scenarios inside Valuation
        assert sentiment_pos < html.index('id="analyst-consensus"') < valuation_pos
        assert valuation_pos < html.index('id="valuation-scenarios"')

    def test_charts_logo_and_company_name_render(self, report_dir):
        render_html_report("TEST")
        content = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        assert "Test Corporation" in content
        # Keyless favicon logo with www. stripped
        assert "favicons?domain=testcorp.com" in content
        # Inline SVG charts: price, revenue, target range, ratings, 52-week
        # range, sentiment trend
        assert 'id="price-chart"' in content
        assert 'id="revenue-chart"' in content
        assert content.count("<svg") == 6

    def test_rating_reads_recommendation_line_not_incidental_words(
        self, tmp_path, monkeypatch
    ):
        """'HOLD (with a Buy-on-confirmation plan)' must render HOLD, not BUY."""
        monkeypatch.setattr(report_tools.settings, "report_output_dir", str(tmp_path))
        sym_dir = tmp_path / "HHH"
        sym_dir.mkdir()
        (sym_dir / "HHH_investment_recommendation.md").write_text(
            "## HHH Investment Recommendation\n\n"
            "### Recommendation: **HOLD (with a Buy-on-confirmation plan)**\n\n"
            "Wait for a breakout before you buy.\n",
            encoding="utf-8",
        )
        result = render_html_report("HHH")
        assert result.get("status") == "success"
        html = next((tmp_path / "HHH" / "html").glob("*.html")).read_text(encoding="utf-8")
        assert 'class="badge hold">HOLD' in html

    def test_renders_even_with_no_specialist_files(self, tmp_path, monkeypatch):
        """An empty report dir must still yield a valid (skeleton) HTML report."""
        monkeypatch.setattr(report_tools.settings, "report_output_dir", str(tmp_path))
        result = render_html_report("EMPTY")
        assert result.get("status") == "success"
        assert list((tmp_path / "EMPTY" / "html").glob("*.html"))

    def test_etf_sector_chart(self, tmp_path, monkeypatch):
        """ETF reports render the sector-allocation chart."""
        monkeypatch.setattr(report_tools.settings, "report_output_dir", str(tmp_path))
        sym_dir = tmp_path / "ETFX"
        sym_dir.mkdir()
        (sym_dir / "ETFX_etf_fundamental_analysis.md").write_text(
            "# ETF Profile\n\nLow-cost index fund.\n", encoding="utf-8"
        )
        chart = dict(_CHART_DATA)
        chart["sector_weightings_pct"] = {"technology": 32.0, "healthcare": 10.0}
        (sym_dir / "ETFX_chart_data.json").write_text(json.dumps(chart), encoding="utf-8")
        render_html_report("ETFX")  # asset type auto-detected from etf_* file
        html = next((sym_dir / "html").glob("*.html")).read_text(encoding="utf-8")
        assert "ETF Research Report" in html
        assert 'id="sector-allocation"' in html
        assert "Technology" in html
