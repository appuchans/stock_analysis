"""Agent for Risk Analyst."""

from typing import List, Any

from .base_agent import BaseAgent
from ..tools.analysis_tools import RiskAnalysisTool
from ..tools.calculation_tools import FinancialCalculatorTool, RiskCalculatorTool


class RiskAnalystAgent(BaseAgent):
    """Agent responsible for risk analyst."""

    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4o"):
        """Initialize the RiskAnalystAgent."""
        super().__init__("risk_analyst", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        """Get risk analyst tools."""
        return [
            RiskAnalysisTool(),
            RiskCalculatorTool(),
            FinancialCalculatorTool(),
        ]
