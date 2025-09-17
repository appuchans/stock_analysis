"""Agent for Risk Analyst."""

from typing import List, Any

from .base_agent import BaseAgent
from ..tools.analysis_tools import RiskAnalysisTool, RiskCalculatorTool, FinancialCalculatorTool
from ..tools.calculation_tools import FinancialCalculatorTool
from ..tools.calculation_tools import RiskCalculatorTool
from ..tools.analysis_tools import RiskAnalysisTool
from ..config.settings import settings


class RiskAnalystAgent(BaseAgent):
    """Agent responsible for risk analyst."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the RiskAnalystAgent."""
        super().__init__("risk_analyst", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get risk analyst tools."""
        return [
            RiskAnalysisTool(),
            RiskCalculatorTool(),
            FinancialCalculatorTool(),
        ]
