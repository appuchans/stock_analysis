"""Agent for Fundamental Analyst."""

from typing import List, Any, Optional

from .base_agent import BaseAgent
from ..tools.analysis_tools import FundamentalAnalysisTool
from ..tools.calculation_tools import FinancialCalculatorTool, ValuationCalculatorTool


class FundamentalAnalystAgent(BaseAgent):
    """Agent responsible for fundamental analyst."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the FundamentalAnalystAgent."""
        super().__init__("fundamental_analyst", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        """Get fundamental analyst tools."""
        return [
            FundamentalAnalysisTool(),
            FinancialCalculatorTool(),
            ValuationCalculatorTool(),
        ]
