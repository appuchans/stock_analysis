"""Agent for Report Generator."""

from typing import List, Any

from .base_agent import BaseAgent
from ..config.settings import settings


class ReportGeneratorAgent(BaseAgent):
    """Agent responsible for report generator."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the ReportGeneratorAgent."""
        super().__init__("report_generator", llm_provider, model)
    
    def _get_tools(self) -> List[Any]:
        """Get report generator tools."""
        return [
        ]
