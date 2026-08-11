"""Agent for Industry Analyst."""

from typing import Any, List, Optional

from ..tools.company_intel import ETFPortfolioTool
from ..tools.free_data_collection import (
    FreeCompetitorAnalysisTool,
    FreeEconomicDataTool,
    FreeFREDTool,
    FreeIndustryAnalysisTool,
    FreeNewsTool,
    FreeWebSearchTool,
    YahooFinanceTool,
)
from .base_agent import BaseAgent


class IndustryAnalystAgent(BaseAgent):
    """Agent responsible for industry analyst."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the IndustryAnalystAgent."""
        super().__init__("industry_analyst", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        """Get industry analyst tools."""
        return [
            YahooFinanceTool(),
            FreeNewsTool(),
            FreeIndustryAnalysisTool(),
            FreeWebSearchTool(),
            ETFPortfolioTool(),
        ]
