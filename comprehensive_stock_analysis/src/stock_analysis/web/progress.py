"""Stage-level progress + a live activity feed for a running analysis.

The stage/progress is driven by CrewAI **Flow method events**
(``MethodExecutionStartedEvent``), which map directly and reliably to the four
pipeline phases — collect_data → specialist analysis → synthesize → report — so
the stepper always advances in lock-step with the flow (no fragile crew-count
math that could stall at the specialist phase). Finer-grained agent/tool events
feed the one-line "what's happening now" ticker.

A single persistent set of listeners forwards to whichever ``StageTracker`` is
active (set by the JobManager around each run) — safe because runs are
serialized. If the event bus isn't importable, progress falls back to the
coarse state the worker sets plus the live token counter; nothing breaks.
"""

import logging
import threading
from typing import Optional, Tuple

_logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active: "Optional[StageTracker]" = None

# Flow method name → (stage label, progress fraction). The specialist phase is a
# single flow method (quick/standard/deep_analysis); per-specialist detail shows
# in the activity ticker instead.
_STAGE_MAP = {
    "collect_data": ("Collecting market & fundamental data", 0.08),
    "quick_analysis": ("Running specialist analysis", 0.20),
    "standard_analysis": ("Running specialist analysis", 0.20),
    "deep_analysis": ("Running specialist analysis", 0.20),
    "synthesize_recommendation": ("Synthesizing recommendation", 0.80),
    "generate_report": ("Generating report", 0.92),
}


class StageTracker:
    """Holds the current (stage label, 0–1 fraction) and latest activity line.

    ``set_stage`` is monotonic so an out-of-order event can never make the bar
    jump backwards.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.stage = "Starting…"
        self.progress = 0.03
        self.activity = ""

    def set_stage(self, label: str, fraction: float) -> None:
        with self._lock:
            if fraction >= self.progress:
                self.stage = label
                self.progress = fraction

    def note(self, text: str) -> None:
        if text:
            with self._lock:
                self.activity = text

    def snapshot(self) -> Tuple[str, float]:
        with self._lock:
            return self.stage, self.progress


def set_active(tracker: Optional[StageTracker]) -> None:
    global _active
    with _lock:
        _active = tracker


def _dispatch_stage(label: str, fraction: float) -> None:
    with _lock:
        tracker = _active
    if tracker is not None:
        tracker.set_stage(label, fraction)


def _dispatch_activity(text: str) -> None:
    with _lock:
        tracker = _active
    if tracker is not None:
        tracker.note(text)


def _task_label(event) -> str:
    """The task being worked on (e.g. 'Risk Analysis') — clearer than the agent
    role ('Senior Risk Analysis Specialist').

    ``task_name`` is populated on tool-usage events, but crewai's
    ``AgentExecutionStartedEvent`` only fills in fingerprint data — its
    ``task_name`` is always empty — so the activity ticker would otherwise
    freeze at the last tool call once a stage (e.g. synthesis/report) runs
    an agent that never invokes a tool. Fall back to the ``Task`` object's
    own ``.name`` in that case.
    """
    name = (getattr(event, "task_name", "") or "").strip()
    if not name:
        task = getattr(event, "task", None)
        name = (getattr(task, "name", "") or "").strip()
    return name[:48]


# One persistent set of bus listeners (best-effort; mirrors crew/event_listener).
try:  # pragma: no cover - exercised only with crewai installed
    from crewai.events import crewai_event_bus
    from crewai.events.types.agent_events import AgentExecutionStartedEvent
    from crewai.events.types.flow_events import (
        MethodExecutionFinishedEvent,
        MethodExecutionStartedEvent,
    )
    from crewai.events.types.tool_usage_events import ToolUsageStartedEvent

    @crewai_event_bus.on(MethodExecutionStartedEvent)
    def _on_method_start(source, event):  # noqa: ANN001
        try:
            mapped = _STAGE_MAP.get(getattr(event, "method_name", "") or "")
            if mapped:
                _dispatch_stage(*mapped)
        except Exception as exc:
            _logger.debug("progress method-start dispatch failed: %s", exc)

    @crewai_event_bus.on(MethodExecutionFinishedEvent)
    def _on_method_finish(source, event):  # noqa: ANN001
        try:
            if (getattr(event, "method_name", "") or "") == "generate_report":
                _dispatch_stage("Finalizing report", 0.98)
        except Exception as exc:
            _logger.debug("progress method-finish dispatch failed: %s", exc)

    @crewai_event_bus.on(AgentExecutionStartedEvent)
    def _on_agent_start(source, event):  # noqa: ANN001
        try:
            task = _task_label(event)
            if task:
                _dispatch_activity(f"{task} — working")
        except Exception as exc:
            _logger.debug("progress agent-start dispatch failed: %s", exc)

    @crewai_event_bus.on(ToolUsageStartedEvent)
    def _on_tool_start(source, event):  # noqa: ANN001
        try:
            task = _task_label(event)
            tool = (getattr(event, "tool_name", "") or "").strip()
            if tool:
                _dispatch_activity(f"{task} · {tool}" if task else tool)
        except Exception as exc:
            _logger.debug("progress tool-start dispatch failed: %s", exc)

    _BUS_AVAILABLE = True
except (ImportError, AttributeError):  # pragma: no cover
    _BUS_AVAILABLE = False
