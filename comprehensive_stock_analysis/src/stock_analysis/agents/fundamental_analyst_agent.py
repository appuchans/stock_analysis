"""Agent for Fundamental Analyst."""

from typing import List, Any

from .base_agent import BaseAgent
from ..tools.analysis_tools import FundamentalAnalysisTool, FinancialCalculatorTool, ValuationCalculatorTool
from ..tools.calculation_tools import FinancialCalculatorTool
from ..tools.calculation_tools import ValuationCalculatorTool
from ..config.settings import settings


class FundamentalAnalystAgent(BaseAgent):
    """Agent responsible for fundamental analyst."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the FundamentalAnalystAgent."""
        super().__init__("fundamental_analyst", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get fundamental analyst tools."""
        return [
            FundamentalAnalysisTool(),
            FinancialCalculatorTool(),
            ValuationCalculatorTool(),
        ]
