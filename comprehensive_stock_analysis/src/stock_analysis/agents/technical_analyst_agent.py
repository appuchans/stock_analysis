"""Technical Analyst Agent for technical analysis of stocks."""

from typing import List, Any

from .base_agent import BaseAgent
from ..tools.analysis_tools import TechnicalAnalysisTool
from ..tools.calculation_tools import TechnicalIndicatorTool, FinancialCalculatorTool


class TechnicalAnalystAgent(BaseAgent):
    """Agent responsible for technical analysis of stocks."""
    
    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the Technical Analyst Agent."""
        super().__init__("technical_analyst", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get technical analysis tools."""
        return [
            TechnicalAnalysisTool(),
            TechnicalIndicatorTool(),
            FinancialCalculatorTool()
        ]
