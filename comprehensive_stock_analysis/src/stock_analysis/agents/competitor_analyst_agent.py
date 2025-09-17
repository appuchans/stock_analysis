"""Agent for Competitor Analyst."""

from typing import List, Any

from .base_agent import BaseAgent
from ..tools.free_data_collection import (
    YahooFinanceTool, FreeNewsTool, FreeFREDTool, 
    FreeEconomicDataTool, FreeWebSearchTool,
    FreeCompetitorAnalysisTool, FreeIndustryAnalysisTool
)
from ..config.settings import settings


class CompetitorAnalystAgent(BaseAgent):
    """Agent responsible for competitor analyst."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the CompetitorAnalystAgent."""
        super().__init__("competitor_analyst", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get competitor analyst tools."""
        return [
            YahooFinanceTool(),
            FreeNewsTool(),
            FreeCompetitorAnalysisTool(),
            FreeWebSearchTool(),
        ]
