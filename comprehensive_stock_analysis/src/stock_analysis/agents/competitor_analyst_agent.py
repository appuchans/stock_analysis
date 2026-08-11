"""Agent for Competitor Analyst."""

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


class CompetitorAnalystAgent(BaseAgent):
    """Agent responsible for competitor analyst."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the CompetitorAnalystAgent."""
        super().__init__("competitor_analyst", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        """Get competitor analyst tools."""
        return [
            YahooFinanceTool(),
            FreeNewsTool(),
            FreeCompetitorAnalysisTool(),
            FreeWebSearchTool(),
            ETFPortfolioTool(),
        ]
