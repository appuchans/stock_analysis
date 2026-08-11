"""Agent for Investment Advisor."""

from typing import Any, List, Optional

from ..tools.analysis_tools import ComparisonTool, ValuationTool
from ..tools.calculation_tools import FinancialCalculatorTool, ValuationCalculatorTool
from ..tools.company_intel import AnalystDataTool
from ..tools.portfolio_tools import PortfolioAnalysisTool
from .base_agent import BaseAgent


class InvestmentAdvisorAgent(BaseAgent):
    """Agent responsible for investment advisor."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the InvestmentAdvisorAgent."""
        super().__init__("investment_advisor", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        """Get investment advisor tools."""
        return [
            ValuationTool(),
            ComparisonTool(),
            ValuationCalculatorTool(),
            FinancialCalculatorTool(),
            AnalystDataTool(),
            PortfolioAnalysisTool(),
        ]
