"""Agent for Report Generator."""

from typing import List, Any, Optional

from .base_agent import BaseAgent
from ..tools.report_tools import ReportGeneratorTool


class ReportGeneratorAgent(BaseAgent):
    """Agent responsible for report generator."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the ReportGeneratorAgent."""
        super().__init__("report_generator", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        return [ReportGeneratorTool()]
