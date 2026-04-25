"""Agent for Industry Analyst."""

from typing import List, Any, Optional

from .base_agent import BaseAgent
from ..tools.free_data_collection import (
    YahooFinanceTool, FreeNewsTool, FreeFREDTool, 
    FreeEconomicDataTool, FreeWebSearchTool,
    FreeCompetitorAnalysisTool, FreeIndustryAnalysisTool
)
from ..config.settings import settings


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
        ]
