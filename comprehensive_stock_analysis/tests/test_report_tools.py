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
        "price_targets": {
            "current_price": 130.0,
            "low": 100.0,
            "mean": 160.0,
            "median": 158.0,
            "high": 220.0,
        },
        "rating_counts": {
            "period": "0m",
            "strong_buy": 10,
            "buy": 40,
            "hold": 5,
            "sell": 1,
            "strong_sell": 0,
        },
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
        {
            "symbol": "TEST",
            "name": "Test Corporation",
            "market_cap_b": 3200.0,
            "pe_ttm": 31.4,
            "fwd_pe": 25.1,
            "revenue_growth_pct": 65.5,
            "operating_margin_pct": 60.4,
            "is_subject": True,
        },
        {
            "symbol": "PEER",
            "name": "Peer Inc",
            "market_cap_b": 900.0,
            "pe_ttm": 40.2,
            "fwd_pe": 30.5,
            "revenue_growth_pct": 20.0,
            "operating_margin_pct": 25.0,
            "is_subject": False,
        },
    ],
    "valuation_scenarios": [
        {
            "scenario": "Bear",
            "growth_pct": 12.0,
            "discount_pct": 12.0,
            "terminal_pct": 2.5,
            "intrinsic_per_share": 123.55,
        },
        {
            "scenario": "Base",
            "growth_pct": 24.0,
            "discount_pct": 10.0,
            "terminal_pct": 2.5,
            "intrinsic_per_share": 209.73,
        },
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

    def test_gaps_go_to_the_run_report_not_the_client_report(self, report_dir):
        """Provenance and coverage notes are operator material.

        Mixing them into the research document made it read like a job log, so
        they are excised from every stage body and written to a separate run
        report instead.
        """
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        # Nothing about data gaps reaches the reader.
        assert 'id="data-sources-gaps"' not in html
        assert "segment revenue not available" not in html

        run_report = report_dir / "TEST" / "TEST_run_report.md"
        assert run_report.exists(), "gaps must be preserved, not discarded"
        body = run_report.read_text(encoding="utf-8")
        assert "segment revenue not available" in body
        assert "Why data was unavailable" in body

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
        html = next((tmp_path / "HHH" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
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
        (sym_dir / "ETFX_chart_data.json").write_text(
            json.dumps(chart), encoding="utf-8"
        )
        render_html_report("ETFX")  # asset type auto-detected from etf_* file
        html = next((sym_dir / "html").glob("*.html")).read_text(encoding="utf-8")
        assert "ETF Research Report" in html
        assert 'id="sector-allocation"' in html
        assert "Technology" in html


class TestMarkdownBlockNormalisation:
    """A list attached directly under its lead-in line must render as a list.

    Python-Markdown only opens a <ul> after a blank line; without one the items
    stay in the preceding paragraph and — because nl2br is enabled — render as
    <br/>-joined text. Agents write that shape constantly, so the renderer
    normalises it (one real AMZN report had 220 such walls of prose).
    """

    def test_attached_list_becomes_a_real_list(self):
        html = report_tools._md_to_html(
            "Key drivers:\n- AWS margin expansion\n- Advertising growth\n"
        )
        assert "<ul>" in html
        assert html.count("<li>") == 2
        assert "<br" not in html

    def test_attached_table_becomes_a_real_table(self):
        html = report_tools._md_to_html(
            "Results:\n| Strategy | Return |\n|---|---|\n| SMA | 12% |\n"
        )
        assert "<table>" in html
        assert "<td>SMA</td>" in html

    def test_numbered_list_attached_to_lead_in(self):
        html = report_tools._md_to_html("Steps:\n1. First\n2. Second\n")
        assert "<ol>" in html
        assert html.count("<li>") == 2

    def test_already_separated_list_is_unchanged(self):
        html = report_tools._md_to_html("Key drivers:\n\n- One\n- Two\n")
        assert html.count("<li>") == 2

    def test_headings_and_blockquotes_are_valid_boundaries(self):
        html = report_tools._md_to_html("## Heading\n- One\n- Two\n")
        assert html.count("<li>") == 2

    def test_fenced_code_block_is_left_alone(self):
        html = report_tools._md_to_html("Example:\n\n```\ntext\n- not a list\n```\n")
        # The dash inside the fence must not be promoted into a list item.
        assert "<li>" not in html

    def test_dash_in_prose_is_not_mistaken_for_a_list(self):
        html = report_tools._md_to_html("Revenue fell 3% - a modest decline.\n")
        assert "<li>" not in html


class TestInlineSourceStripping:
    """Report prose must read as a professional document.

    The stage prompts forbid inline provenance, but models still emit it and
    reports already on disk were written under older instructions — so the
    renderer strips it. Provenance survives in the closing Data Sources & Gaps
    section, which is where it belongs.
    """

    def test_source_parenthetical_removed(self):
        out = report_tools._strip_inline_sources(
            "RSI 54.35 (source: *pre-computed indicators*) shows momentum."
        )
        assert out == "RSI 54.35 shows momentum."

    def test_same_source_removed(self):
        out = report_tools._strip_inline_sources("Revenue rose 11% (*same source*).")
        assert out == "Revenue rose 11%."

    def test_as_of_note_removed(self):
        out = report_tools._strip_inline_sources(
            "Price is $253 (as of **2026-08-14**) and rising."
        )
        assert out == "Price is $253 and rising."

    def test_bracketed_source_removed(self):
        out = report_tools._strip_inline_sources(
            "Margins expanded [source: Yahoo Finance] materially."
        )
        assert out == "Margins expanded materially."

    def test_tool_name_never_reaches_the_reader(self):
        out = report_tools._strip_inline_sources(
            "The yield is 4.7% (Source: proxies from `free_economic_data_collector`)."
        )
        assert "free_economic_data_collector" not in out
        assert "4.7%" in out

    def test_machine_field_paths_removed(self):
        out = report_tools._strip_inline_sources(
            "Bullish share was 62% (source: `social.stocktwits`)."
        )
        assert "social.stocktwits" not in out

    def test_ordinary_parenthetical_is_preserved(self):
        text = "EBITDA margin improved to 12% (up from 9%)."
        assert report_tools._strip_inline_sources(text) == text

    def test_fiscal_period_in_prose_is_preserved(self):
        text = "Revenue was $130,497M in FY2025, up 11% year over year."
        assert report_tools._strip_inline_sources(text) == text

    def test_sources_appendix_is_kept_but_demachined(self):
        out = report_tools._strip_inline_sources(
            "## Data Sources & Gaps\n- Yahoo Finance (source label: `analyst_x`)\n"
        )
        assert "Data Sources & Gaps" in out
        assert "Yahoo Finance" in out
        assert "analyst_x" not in out

    def test_table_rows_are_not_corrupted(self):
        text = "| Metric | Value |\n|---|---|\n| Revenue | $130M |"
        assert report_tools._strip_inline_sources(text) == text

    def test_citation_only_line_is_dropped_not_left_as_a_stub(self):
        out = report_tools._strip_inline_sources("Revenue grew.\n- (source: Yahoo)\n")
        assert "Revenue grew." in out
        assert "source" not in out.lower()

    def test_runs_in_linear_time_on_pathological_input(self):
        """The first attempt at this regex backtracked catastrophically."""
        import time

        text = ("Some prose with (a paren " * 400) + "source: x)\n"
        start = time.time()
        report_tools._strip_inline_sources(text)
        assert time.time() - start < 2.0

    def test_standalone_source_line_is_dropped(self):
        out = report_tools._strip_inline_sources(
            "Revenue grew 12%.\n\n**Source:** user-provided data (collected data).\n\nMargins held."
        )
        assert "Revenue grew 12%." in out
        assert "Margins held." in out
        assert "Source" not in out

    def test_sources_appendix_heading_is_not_dropped(self):
        out = report_tools._strip_inline_sources(
            "## Data Sources & Gaps\n\n- Yahoo Finance statements\n"
        )
        assert "Data Sources & Gaps" in out
        assert "Yahoo Finance statements" in out


class TestLeadInLabelEmphasis:
    """Memo items are written as 'Label<newline>body'.

    With nl2br that becomes 'Label<br/>body' inside one paragraph, and with no
    emphasis the label melts into the prose — which is what makes appendices
    read as walls of text even when the paragraphs are short.
    """

    def test_short_label_before_body_is_bolded(self):
        html = report_tools._md_to_html(
            "Track record\nManagement has delivered meaningful operational "
            "improvement since the post-pandemic cost reset, with revenue up.\n"
        )
        assert "<strong>Track record</strong>" in html

    def test_label_inside_a_list_item_is_bolded(self):
        html = report_tools._md_to_html(
            "- Our view — Buy\n  Buy Amazon for its unusually strong collection "
            "of businesses, not merely because it is a large online store.\n"
        )
        assert "<strong>Our view — Buy</strong>" in html

    def test_a_finished_sentence_is_not_treated_as_a_label(self):
        """Prose that happens to wrap must not get its first line bolded."""
        html = report_tools._md_to_html(
            "Revenue grew 12% in FY2025.\nMargins expanded on the back of AWS "
            "and advertising, both of which carry higher incremental margins.\n"
        )
        assert "<strong>" not in html

    def test_two_short_lines_are_left_alone(self):
        """Needs real body text after the break, not another short line."""
        html = report_tools._md_to_html("Alpha\nBeta\n")
        assert "<strong>" not in html

    def test_existing_bold_label_is_not_double_wrapped(self):
        html = report_tools._md_to_html(
            "**Margins.** Operating margin expanded to 11.8% in FY2025 on "
            "stronger AWS contribution and tighter fulfillment costs.\n"
        )
        assert "<strong><strong>" not in html

    def test_label_emphasis_does_not_alter_the_words(self):
        text = "Track record\n" + "Management delivered. " * 8
        html = report_tools._md_to_html(text)
        import re

        stripped = re.sub(r"<[^>]+>", "", html)
        assert "Track record" in stripped
        assert stripped.count("Management delivered.") == 8


class TestRunCommentaryStripping:
    """The client report must never narrate the pipeline.

    Which source answered, what a run did or did not fetch, and what was
    retried are operator concerns — they belong in the run report. Left in the
    body they make a research document read like a job log.
    """

    def test_parenthetical_run_note_removed(self):
        out = report_tools._strip_inline_sources(
            "From market-traded proxies (since FRED was unavailable in this run): "
            "the 10-year yield is 4.7%."
        )
        assert "FRED" not in out
        assert "4.7%" in out

    def test_trailing_in_this_run_clause_removed(self):
        out = report_tools._strip_inline_sources(
            "Direct peer margin comparisons are not covered in this run."
        )
        assert "in this run" not in out
        assert "peer margin comparisons" in out

    def test_subject_position_narration_drops_the_sentence(self):
        """Deleting the phrase alone would leave a headless sentence."""
        out = report_tools._strip_inline_sources(
            "Your provided dataset does not include regulatory text. "
            "Pega competes in low-code automation."
        )
        assert "provided dataset" not in out
        assert "Pega competes in low-code automation." in out

    def test_placeholder_not_available_row_is_dropped(self):
        out = report_tools._strip_inline_sources(
            "**Quantitative peer metrics:** not available from provided dataset."
        )
        assert out.strip() == ""

    def test_see_data_sources_pointer_removed(self):
        out = report_tools._strip_inline_sources(
            "Those figures are omitted (see Data Sources & Gaps)."
        )
        assert "Data Sources" not in out

    def test_ordinary_analysis_prose_is_untouched(self):
        text = (
            "Revenue grew 12% in FY2025. Margins expanded on AWS strength, "
            "and the company operates in three segments (retail, cloud, ads)."
        )
        assert report_tools._strip_inline_sources(text) == text

    def test_the_word_run_in_business_prose_survives(self):
        """'run' is a common business verb — only pipeline phrasing goes."""
        text = "Management continues to run the marketplace at scale."
        assert report_tools._strip_inline_sources(text) == text


class TestPrintStylesheet:
    """A PDF of the report must contain the appendices.

    The app embeds the report in an iframe sandboxed without `allow-scripts`,
    so the beforeprint handler that opens each <details> never runs there. The
    print stylesheet therefore has to force appendix content visible on its
    own — otherwise "Download PDF" silently produces a report with every
    specialist workpaper collapsed away.
    """

    def test_appendices_are_forced_visible_without_script(self, report_dir):
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        assert "details.detail-section > *" in html
        assert "display: revert" in html

    def test_page_setup_and_typographic_widows_are_handled(self, report_dir):
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        assert "@page" in html
        assert "orphans" in html and "widows" in html
        # A heading must not be the last thing on a page.
        assert "page-break-after: avoid" in html

    def test_navigation_chrome_is_hidden_in_print(self, report_dir):
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        print_css = html.split("@media print")[1]
        # Table of contents and the floating back-to-top control are screen
        # affordances with no meaning on paper.
        assert ".toc, .to-top { display: none; }" in print_css

    def test_beforeprint_handler_still_present_for_standalone_viewing(
        self, report_dir
    ):
        """Belt and braces: when the report is opened directly, script runs and
        opens the panels too, so they are expanded on screen as well as in the
        PDF."""
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        assert "beforeprint" in html

    def test_pdf_carries_page_furniture(self, report_dir):
        """A printed copy must be identifiable once it leaves the screen."""
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        assert "@page" in html
        assert 'content: "TEST — Equity Research"' in html
        assert "counter(page)" in html and "counter(pages)" in html
        assert "not investment advice" in html
        # The cover page should not repeat the running header.
        assert "@page :first" in html

    def test_etf_print_header_says_etf(self, tmp_path, monkeypatch):
        monkeypatch.setattr(report_tools.settings, "report_output_dir", str(tmp_path))
        d = tmp_path / "ETFX"
        d.mkdir()
        (d / "ETFX_etf_fundamental_analysis.md").write_text(
            "# ETF Profile\n\nLow-cost index fund.\n", encoding="utf-8"
        )
        render_html_report("ETFX")
        html = next((d / "html").glob("*.html")).read_text(encoding="utf-8")
        assert 'content: "ETFX — ETF Research"' in html

    def test_print_links_expose_their_target(self, report_dir):
        """An href is invisible on paper; in-page anchors stay silent."""
        render_html_report("TEST")
        html = next((report_dir / "TEST" / "html").glob("*.html")).read_text(
            encoding="utf-8"
        )
        assert 'a[href^="http"]::after' in html
        assert 'a[href^="#"]::after { content: none; }' in html
