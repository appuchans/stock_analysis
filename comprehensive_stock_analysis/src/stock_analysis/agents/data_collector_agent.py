"""Data Collector Agent for comprehensive stock data gathering."""

from typing import List, Any

from .base_agent import BaseAgent
from ..tools.free_data_collection import (
    YahooFinanceTool, FreeSECFilingTool, FreeFREDTool,
    FreeNewsTool, FreeEconomicDataTool, FreeWebSearchTool,
    FreeCompetitorAnalysisTool, FreeIndustryAnalysisTool,
    ParallelDataCollectionTool,
)
from ..config.settings import settings


class DataCollectorAgent(BaseAgent):
    """Agent responsible for collecting comprehensive stock data from multiple sources."""
    
    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the Data Collector Agent."""
        super().__init__("data_collector", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get data collection tools (all free)."""
        tools = []
        
        # Parallel collector — fetches all enabled sources concurrently
        tools.append(ParallelDataCollectionTool())

        # Individual tools kept for targeted queries by the agent
        tools.append(YahooFinanceTool())
        
        # Free SEC filings
        if settings.sec_edgar_enabled:
            tools.append(FreeSECFilingTool())
        
        # Free FRED economic data
        if settings.fred_enabled:
            tools.append(FreeFREDTool(api_key=settings.fred_api_key))
        
        # Free news data
        if settings.rss_feeds_enabled:
            tools.append(FreeNewsTool())
        
        # Free economic data
        tools.append(FreeEconomicDataTool(fred_api_key=settings.fred_api_key))
        
        # Free web search
        if settings.web_scraping_enabled:
            tools.append(FreeWebSearchTool())
        
        # Free competitor analysis
        tools.append(FreeCompetitorAnalysisTool())
        
        # Free industry analysis
        tools.append(FreeIndustryAnalysisTool())
        
        return tools
