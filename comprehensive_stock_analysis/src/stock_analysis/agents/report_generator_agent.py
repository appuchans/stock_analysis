"""Agent for Report Generator."""

from typing import List, Any, Optional

from .base_agent import BaseAgent


class ReportGeneratorAgent(BaseAgent):
    """Agent responsible for writing the synthesized research narrative.

    Deliberately tool-less: HTML rendering is deterministic code
    (report_tools.render_html_report), so this agent's only job is writing
    the narrative markdown. Giving it the render tool caused it to invoke
    the tool and return a status summary instead of the document.
    """

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the ReportGeneratorAgent."""
        super().__init__("report_generator", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        return []
