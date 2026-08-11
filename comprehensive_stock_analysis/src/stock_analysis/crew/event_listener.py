"""Structured CrewAI event listener — prints clean task progress to stdout."""

import logging

_logger = logging.getLogger(__name__)

# Human-readable names for task keys
_TASK_LABELS = {
    "data_collection": "Data Collection",
    "technical_analysis": "Technical Analysis",
    "fundamental_analysis": "Fundamental Analysis",
    "risk_analysis": "Risk Analysis",
    "sentiment_analysis": "Sentiment Analysis",
    "market_analysis": "Market Analysis",
    "industry_analysis": "Industry Analysis",
    "competitor_analysis": "Competitor Analysis",
    "economic_analysis": "Economic Analysis",
    "investment_recommendation": "Investment Recommendation",
    "report_generation": "Report Generation",
}


def _label(raw: str) -> str:
    key = str(raw).lower().replace(" ", "_").replace("-", "_")
    return _TASK_LABELS.get(key, raw)


try:
    from crewai.events.base_event_listener import BaseEventListener

    class StockAnalysisEventListener(BaseEventListener):
        """Log concise task/agent progress at DEBUG (no extra console output —
        main.py already reports token usage at end of run). Also tracks tool
        telemetry (call counts, errors, cache hits, latency) via the tool_telemetry
        module for end-of-run observability."""

        def setup_listeners(self, crewai_event_bus):
            try:
                from crewai.events.types.agent_events import AgentExecutionStartedEvent
                from crewai.events.types.crew_events import CrewKickoffCompletedEvent
                from crewai.events.types.task_events import TaskCompletedEvent
                from crewai.events.types.tool_usage_events import (
                    ToolUsageErrorEvent,
                    ToolUsageFinishedEvent,
                    ToolUsageStartedEvent,
                )

                @crewai_event_bus.on(TaskCompletedEvent)
                def on_task_complete(source, event):
                    name = _label(
                        getattr(event, "task_name", "") or getattr(event, "task", "")
                    )
                    _logger.debug("[task-complete] %s", name)

                @crewai_event_bus.on(AgentExecutionStartedEvent)
                def on_agent_start(source, event):
                    _logger.debug("[agent-start] %s", getattr(event, "agent_role", ""))

                @crewai_event_bus.on(CrewKickoffCompletedEvent)
                def on_crew_complete(source, event):
                    usage = getattr(event, "usage_metrics", None)
                    _logger.debug("[crew-complete] token_usage=%s", usage)

                @crewai_event_bus.on(ToolUsageStartedEvent)
                def on_tool_start(source, event):
                    tool_name = getattr(event, "tool_name", "unknown")
                    _logger.debug("[tool-start] %s", tool_name)
                    try:
                        from .. import tool_telemetry

                        tool_telemetry.record_tool_start(tool_name)
                    except Exception:
                        pass

                @crewai_event_bus.on(ToolUsageFinishedEvent)
                def on_tool_finish(source, event):
                    tool_name = getattr(event, "tool_name", "unknown")
                    started_at = getattr(event, "started_at", None)
                    finished_at = getattr(event, "finished_at", None)
                    from_cache = getattr(event, "from_cache", False)
                    duration_ms = 0.0
                    if started_at and finished_at:
                        try:
                            duration_ms = (
                                finished_at - started_at
                            ).total_seconds() * 1000
                        except Exception:
                            pass
                    _logger.debug(
                        "[tool-finish] %s (%.1fms, cached=%s)",
                        tool_name,
                        duration_ms,
                        from_cache,
                    )
                    try:
                        from .. import tool_telemetry

                        tool_telemetry.record_tool_finish(
                            tool_name, duration_ms, from_cache
                        )
                    except Exception:
                        pass

                @crewai_event_bus.on(ToolUsageErrorEvent)
                def on_tool_error(source, event):
                    tool_name = getattr(event, "tool_name", "unknown")
                    error = getattr(event, "error", "unknown error")
                    error_str = str(error)[:200]
                    _logger.warning("[tool-error] %s: %s", tool_name, error_str)
                    try:
                        from .. import tool_telemetry

                        tool_telemetry.record_tool_error(tool_name)
                    except Exception:
                        pass

            except (ImportError, AttributeError):
                pass

    event_listener = StockAnalysisEventListener()

except (ImportError, AttributeError):
    event_listener = None
