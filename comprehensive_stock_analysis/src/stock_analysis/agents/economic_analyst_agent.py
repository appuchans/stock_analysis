"""Agent for Economic Analyst."""

from typing import List, Any

from .base_agent import BaseAgent
from ..tools.free_data_collection import (
    YahooFinanceTool, FreeNewsTool, FreeFREDTool, 
    FreeEconomicDataTool, FreeWebSearchTool,
    FreeCompetitorAnalysisTool, FreeIndustryAnalysisTool
)
from ..config.settings import settings


class EconomicAnalystAgent(BaseAgent):
    """Agent responsible for economic analyst."""
    
    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the EconomicAnalystAgent."""
        super().__init__("economic_analyst", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get economic analyst tools."""
        return [
            FreeFREDTool(api_key=settings.fred_api_key),
            FreeEconomicDataTool(fred_api_key=settings.fred_api_key),
            FreeWebSearchTool(),
        ]
