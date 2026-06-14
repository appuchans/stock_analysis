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
    from crewai.utilities.events import crewai_event_bus
    from crewai.utilities.events.base_event_listener import BaseEventListener

    class StockAnalysisEventListener(BaseEventListener):
        """Print concise task progress and suppress all other CrewAI console output."""

        def setup_listeners(self, crewai_event_bus):
            try:
                from crewai.utilities.events.crewai_events import (
                    AgentActionTakenEvent,
                    CrewKickoffCompleteEvent,
                    TaskCompletedEvent,
                )

                @crewai_event_bus.on(TaskCompletedEvent)
                def on_task_complete(source, event):
                    name = _label(getattr(event, "task_name", "") or getattr(event, "task", ""))
                    _logger.debug("[task-complete] %s", name)

                @crewai_event_bus.on(AgentActionTakenEvent)
                def on_agent_action(source, event):
                    _logger.debug(
                        "[agent-action] %s | tool=%s",
                        getattr(event, "agent_role", ""),
                        getattr(event, "tool", ""),
                    )

                @crewai_event_bus.on(CrewKickoffCompleteEvent)
                def on_crew_complete(source, event):
                    usage = getattr(event, "usage_metrics", None)
                    if usage:
                        total = getattr(usage, "total_tokens", None)
                        if total:
                            print(f"  Tokens used: {total:,}", flush=True)
                    _logger.info("[crew-complete] token_usage=%s", usage)

            except (ImportError, AttributeError):
                pass

    event_listener = StockAnalysisEventListener()

except (ImportError, AttributeError):
    event_listener = None
