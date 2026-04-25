"""Structured CrewAI event listener for observability."""

import logging

_logger = logging.getLogger(__name__)

try:
    from crewai.utilities.events import crewai_event_bus
    from crewai.utilities.events.base_event_listener import BaseEventListener

    class StockAnalysisEventListener(BaseEventListener):
        """Log structured CrewAI events for observability."""

        def setup_listeners(self, crewai_event_bus):
            try:
                from crewai.utilities.events.crewai_events import (
                    AgentActionTakenEvent,
                    CrewKickoffCompleteEvent,
                    TaskCompletedEvent,
                )

                @crewai_event_bus.on(TaskCompletedEvent)
                def on_task_complete(source, event):
                    _logger.info(
                        "[task-complete] %s | output_length=%d",
                        getattr(event, "task_name", "unknown"),
                        len(str(getattr(event, "output", ""))),
                    )

                @crewai_event_bus.on(AgentActionTakenEvent)
                def on_agent_action(source, event):
                    _logger.debug(
                        "[agent-action] %s | tool=%s",
                        getattr(event, "agent_role", "unknown"),
                        getattr(event, "tool", "unknown"),
                    )

                @crewai_event_bus.on(CrewKickoffCompleteEvent)
                def on_crew_complete(source, event):
                    _logger.info(
                        "[crew-complete] token_usage=%s",
                        getattr(event, "usage_metrics", "unavailable"),
                    )

            except (ImportError, AttributeError):
                pass  # event types not available in this crewai version

    # Register singleton at import time
    event_listener = StockAnalysisEventListener()

except (ImportError, AttributeError):
    # crewai.utilities.events not available; fall back silently
    event_listener = None
