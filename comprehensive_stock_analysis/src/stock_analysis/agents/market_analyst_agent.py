"""Agent for Market Analyst."""

from typing import List, Any, Optional

from .base_agent import BaseAgent
from ..tools.free_data_collection import (
    YahooFinanceTool, FreeNewsTool, FreeFREDTool, 
    FreeEconomicDataTool, FreeWebSearchTool,
    FreeCompetitorAnalysisTool, FreeIndustryAnalysisTool
)
from ..config.settings import settings


class MarketAnalystAgent(BaseAgent):
    """Agent responsible for market analyst."""
    
    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the MarketAnalystAgent."""
        super().__init__("market_analyst", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get market analyst tools."""
        return [
            YahooFinanceTool(),
            FreeEconomicDataTool(fred_api_key=settings.fred_api_key),
            FreeWebSearchTool(),
        ]
