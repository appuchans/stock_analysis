"""Guards for the flow stage prompt configuration (config/flow_tasks.yaml)."""

import re

import pytest

from src.stock_analysis.config.loader import config_loader

# Every {placeholder} referenced in flow_tasks.yaml must be provided at kickoff
# by StockAnalysisFlow ( _inputs() plus per-stage extras), or CrewAI's
# interpolation will fail at runtime.
_KNOWN_INPUTS = {
    "symbol",
    "asset_type",
    "collected_data",
    "technical_data",
    "analyst_data",
    "financials_data",
    "ownership_data",
    "sentiment_data",
    "statements_10y_data",  # deep runs only, when FMP_API_KEY is configured
    "transcript_data",  # deep runs only, when FMP_API_KEY is configured
    "segments_data",  # any depth, when FMP_API_KEY is configured
    "filing_sections_data",  # any depth, when SEC_API_KEY is configured
    "earnings_surprises_data",  # any depth, when FINNHUB_API_KEY is configured
    "peers_data",  # any depth, when FMP or Finnhub is configured
    "shareholder_returns_data",  # any depth, when FMP_API_KEY is configured
    "analyses_summary",  # passed by synthesize_recommendation / generate_report
    "historical_context",  # passed by synthesize_recommendation from past rec_history
    "analysis_key",  # passed per stage by _run_stages
}

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


# Rendered in Python (web/rec_summary.py), not by a CrewAI kickoff.
_NON_FLOW_TASKS = {"recommendation_summary"}


def _walk_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_strings(v)


class TestFlowTasksConfig:
    def test_loads_with_required_sections(self):
        cfg = config_loader.load_flow_tasks_config()
        for key in (
            "shared",
            "collect_data",
            "technical",
            "fundamental",
            "risk",
            "sentiment",
            "market",
            "industry",
            "competitor",
            "economic",
            "recommendation",
            "report",
        ):
            assert key in cfg, f"missing section: {key}"
        assert "rigor_footer" in cfg["shared"]
        assert "with_data_suffix" in cfg["shared"]
        assert "stage_expected_output" in cfg["shared"]

    def test_all_placeholders_are_known_inputs(self):
        cfg = config_loader.load_flow_tasks_config()
        # recommendation_summary is not a flow stage: web/rec_summary.py renders
        # it with str.format() from an existing report, so its placeholders are
        # never supplied by a CrewAI kickoff and this guard does not apply.
        cfg = {k: v for k, v in cfg.items() if k not in _NON_FLOW_TASKS}
        unknown = set()
        for text in _walk_strings(cfg):
            unknown |= set(_PLACEHOLDER_RE.findall(text)) - _KNOWN_INPUTS
        assert not unknown, f"placeholders without kickoff inputs: {sorted(unknown)}"

    def test_standalone_summary_task_is_renderable(self):
        """It sits in the same file, so guard it the way it is actually used."""
        cfg = config_loader.load_flow_tasks_config()
        task = cfg["recommendation_summary"]
        rendered = task["description"].format(
            symbol="TEST",
            recommendation="Hold",
            performance="…",
            reasoning="…",
            key_factors="…",
            risks="…",
            opportunities="…",
        )
        assert "{" not in rendered, "every placeholder must be supplied"

    def test_stock_etf_variants_present(self):
        cfg = config_loader.load_flow_tasks_config()
        for key in (
            "fundamental",
            "industry",
            "competitor",
            "recommendation",
            "risk",
        ):
            assert "stock" in cfg[key] and "etf" in cfg[key]

    def test_flow_builds_descriptions_from_yaml(self):
        from src.stock_analysis.crew.flow_crew import StockAnalysisFlow

        flow = StockAnalysisFlow()
        flow.state.symbol = "TEST"
        flow.state.asset_type = "stock"
        desc = flow._with_data(flow._desc_for("risk"))
        assert "{financials_data}" in desc
        assert "RIGOR REQUIREMENTS" in desc
        assert "{collected_data}" in desc
        # Technical builder honours brief/backtest switches
        deep_tech = flow._desc_technical(brief=False, backtest=True)
        assert "Backtest Tool" in deep_tech
        std_tech = flow._desc_technical(brief=True)
        assert "Backtest Tool" not in std_tech
        # ETF variant switches with asset type
        flow.state.asset_type = "etf"
        assert "expense ratio" in flow._desc_for("fundamental").lower()
        # Recommendation's ETF variant must instruct against framing missing
        # analyst coverage as a data gap, and must not need {analyst_data}
        etf_rec = flow._desc_for("recommendation")
        assert "not a data gap" in etf_rec.lower()
        assert "{analyst_data}" not in etf_rec


class TestEtfPromptsDoNotReportCompanyDataAsMissing:
    """An ETF has no insiders and no operating balance sheet.

    Prompts that ask for those produce sections apologising for absent data —
    a real XME report devoted a heading to explaining it could not quantify
    insider-selling pressure. Their absence is normal, not a gap.
    """

    def _desc(self, key, asset_type):
        from src.stock_analysis.crew.flow_crew import StockAnalysisFlow

        flow = StockAnalysisFlow()
        flow.state.symbol = "TEST"
        flow.state.asset_type = asset_type
        return flow._desc_for(key)

    def test_etf_risk_prompt_excludes_insider_analysis(self):
        etf = self._desc("risk", "etf").lower()
        assert "do not discuss insider" in etf
        assert "{ownership_data}" not in etf

    def test_stock_risk_prompt_still_covers_insider_activity(self):
        stock = self._desc("risk", "stock")
        assert "{ownership_data}" in stock
        assert "open-market" in stock.lower()

    def test_etf_risk_prompt_covers_fund_specific_risk(self):
        etf = self._desc("risk", "etf").lower()
        for expected in ("concentration", "tracking", "liquidity"):
            assert expected in etf
