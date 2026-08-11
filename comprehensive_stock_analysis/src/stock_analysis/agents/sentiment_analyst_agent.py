"""Agent for Sentiment Analyst."""

from typing import Any, List, Optional

from ..tools.company_intel import AnalystDataTool, OptionsSentimentTool
from ..tools.free_data_collection import (
    FreeNewsTool,
    FreeWebSearchTool,
    YahooFinanceTool,
)
from ..tools.social_sentiment import SocialSentimentTool
from .base_agent import BaseAgent


class SentimentAnalystAgent(BaseAgent):
    """Agent responsible for sentiment analyst."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the SentimentAnalystAgent."""
        super().__init__("sentiment_analyst", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        """Get sentiment analyst tools."""
        return [
            SocialSentimentTool(),
            AnalystDataTool(),
            FreeNewsTool(),
            OptionsSentimentTool(),
            YahooFinanceTool(),
            # Fallback: fills qualitative gaps when a platform source is unavailable
            FreeWebSearchTool(),
        ]
