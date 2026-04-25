"""Agent for Sentiment Analyst."""

from typing import List, Any

from .base_agent import BaseAgent
from ..tools.free_data_collection import (
    YahooFinanceTool, FreeNewsTool, FreeFREDTool, 
    FreeEconomicDataTool, FreeWebSearchTool,
    FreeCompetitorAnalysisTool, FreeIndustryAnalysisTool
)
from ..config.settings import settings


class SentimentAnalystAgent(BaseAgent):
    """Agent responsible for sentiment analyst."""
    
    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the SentimentAnalystAgent."""
        super().__init__("sentiment_analyst", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get sentiment analyst tools."""
        return [
            FreeNewsTool(),
        ]
