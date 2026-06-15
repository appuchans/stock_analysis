"""Stage-level progress + a live activity feed for a running analysis.

Each flow stage runs one crew via ``flow_crew._run_crew`` and fires a
``CrewKickoffCompletedEvent``; we count those to advance the stepper. We also
tap finer-grained agent/tool events to surface a one-line "what's happening
now" ticker. A single persistent listener forwards to whichever
``StageTracker`` is active (set by the JobManager around each run) — safe
because runs are serialized.

If the event bus isn't importable, progress falls back to the coarse state the
worker sets plus the live token counter; nothing breaks.
"""

import logging
import threading
from typing import Optional, Tuple

_logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active: "Optional[StageTracker]" = None


class StageTracker:
    """Turns crew-completion counts into a (stage label, 0–1 fraction) and
    holds the latest activity line."""

    def __init__(self, n_specialists: int):
        self.n = max(int(n_specialists), 1)
        self._completed = 0
        self._lock = threading.Lock()
        self.stage = "Collecting data"
        self.progress = 0.03
        self.activity = ""

    def on_crew_complete(self) -> None:
        with self._lock:
            self._completed += 1
            c = self._completed
            self.stage, self.progress = self._compute(c)

    def note(self, text: str) -> None:
        if text:
            with self._lock:
                self.activity = text

    def _compute(self, c: int) -> Tuple[str, float]:
        n = self.n
        if c <= 0:
            return "Collecting data", 0.03
        if c == 1:
            return "Running specialist analysis", 0.12
        if c <= 1 + n:
            return "Running specialist analysis", 0.12 + 0.60 * ((c - 1) / n)
        if c == 2 + n:
            return "Synthesizing recommendation", 0.85
        return "Generating report", 0.95

    def snapshot(self) -> Tuple[str, float]:
        with self._lock:
            return self.stage, self.progress


def set_active(tracker: Optional[StageTracker]) -> None:
    global _active
    with _lock:
        _active = tracker


def _dispatch_crew_complete() -> None:
    with _lock:
        tracker = _active
    if tracker is not None:
        tracker.on_crew_complete()


def _dispatch_activity(text: str) -> None:
    with _lock:
        tracker = _active
    if tracker is not None:
        tracker.note(text)


def _task_label(event) -> str:
    """The task being worked on (e.g. 'Risk Analysis') — clearer than the agent
    role ('Senior Risk Analysis Specialist')."""
    name = (getattr(event, "task_name", "") or "").strip()
    return name[:48]


# One persistent set of bus listeners (best-effort; mirrors crew/event_listener).
try:  # pragma: no cover - exercised only with crewai installed
    from crewai.events import crewai_event_bus
    from crewai.events.types.agent_events import AgentExecutionStartedEvent
    from crewai.events.types.crew_events import CrewKickoffCompletedEvent
    from crewai.events.types.tool_usage_events import ToolUsageStartedEvent

    @crewai_event_bus.on(CrewKickoffCompletedEvent)
    def _on_crew_complete(source, event):  # noqa: ANN001
        try:
            _dispatch_crew_complete()
        except Exception as exc:
            _logger.debug("progress crew-complete dispatch failed: %s", exc)

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
