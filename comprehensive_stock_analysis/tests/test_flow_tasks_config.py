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
    "analyses_summary",   # passed by synthesize_recommendation / generate_report
    "analysis_key",       # passed per stage by _run_stages
}

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


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
        for key in ("shared", "collect_data", "technical", "fundamental",
                    "risk", "sentiment", "market", "industry", "competitor",
                    "economic", "recommendation", "report"):
            assert key in cfg, f"missing section: {key}"
        assert "rigor_footer" in cfg["shared"]
        assert "with_data_suffix" in cfg["shared"]
        assert "stage_expected_output" in cfg["shared"]

    def test_all_placeholders_are_known_inputs(self):
        cfg = config_loader.load_flow_tasks_config()
        unknown = set()
        for text in _walk_strings(cfg):
            unknown |= set(_PLACEHOLDER_RE.findall(text)) - _KNOWN_INPUTS
        assert not unknown, f"placeholders without kickoff inputs: {sorted(unknown)}"

    def test_stock_etf_variants_present(self):
        cfg = config_loader.load_flow_tasks_config()
        for key in ("fundamental", "industry", "competitor"):
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
