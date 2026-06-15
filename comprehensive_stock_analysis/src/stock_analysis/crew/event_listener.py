"""Structured CrewAI event listener — prints clean task progress to stdout."""

import logging

_logger = logging.getLogger(__name__)

# Human-readable names for task keys
_TASK_LABELS = {
    "data_collection":          "Data Collection",
    "technical_analysis":       "Technical Analysis",
    "fundamental_analysis":     "Fundamental Analysis",
    "risk_analysis":            "Risk Analysis",
    "sentiment_analysis":       "Sentiment Analysis",
    "market_analysis":          "Market Analysis",
    "industry_analysis":        "Industry Analysis",
    "competitor_analysis":      "Competitor Analysis",
    "economic_analysis":        "Economic Analysis",
    "investment_recommendation": "Investment Recommendation",
    "report_generation":        "Report Generation",
}


def _label(raw: str) -> str:
    key = str(raw).lower().replace(" ", "_").replace("-", "_")
    return _TASK_LABELS.get(key, raw)


try:
    from crewai.events import crewai_event_bus
    from crewai.events.base_event_listener import BaseEventListener

    class StockAnalysisEventListener(BaseEventListener):
        """Log concise task/agent progress at DEBUG (no extra console output —
        main.py already reports token usage at end of run)."""

        def setup_listeners(self, crewai_event_bus):
            try:
                from crewai.events.types.agent_events import AgentExecutionStartedEvent
                from crewai.events.types.crew_events import CrewKickoffCompletedEvent
                from crewai.events.types.task_events import TaskCompletedEvent

                @crewai_event_bus.on(TaskCompletedEvent)
                def on_task_complete(source, event):
                    name = _label(getattr(event, "task_name", "") or getattr(event, "task", ""))
                    _logger.debug("[task-complete] %s", name)

                @crewai_event_bus.on(AgentExecutionStartedEvent)
                def on_agent_start(source, event):
                    _logger.debug("[agent-start] %s", getattr(event, "agent_role", ""))

                @crewai_event_bus.on(CrewKickoffCompletedEvent)
                def on_crew_complete(source, event):
                    usage = getattr(event, "usage_metrics", None)
                    _logger.debug("[crew-complete] token_usage=%s", usage)

            except (ImportError, AttributeError):
                pass

    event_listener = StockAnalysisEventListener()

except (ImportError, AttributeError):
    event_listener = None
