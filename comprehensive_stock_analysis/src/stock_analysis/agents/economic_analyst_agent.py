"""Agent for Economic Analyst."""

from typing import Any, List, Optional

from ..config.settings import settings
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
