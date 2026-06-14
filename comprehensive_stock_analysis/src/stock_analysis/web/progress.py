"""Stage-level progress tracking for a running analysis.

Each flow stage runs one crew via ``flow_crew._run_crew`` and fires a
``CrewKickoffCompleteEvent``. We register a single persistent listener on the
CrewAI event bus that forwards completions to whichever ``StageTracker`` is
currently active (set by the JobManager around each run). Because runs are
serialized, there is never more than one active tracker — this sidesteps the
need to unsubscribe a per-run listener.

If the event bus isn't importable, progress falls back to whatever coarse
state the worker sets plus the live token counter; nothing breaks.
"""

import logging
import threading
from typing import Optional, Tuple

_logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active: "Optional[StageTracker]" = None


class StageTracker:
    """Turns crew-completion counts into a (stage label, 0–1 fraction).

    Crew completion order within a run: collect_data (1) → specialist stages
    (N, concurrent) → synthesize_recommendation (1) → generate_report (1).
    """

    def __init__(self, n_specialists: int):
        self.n = max(int(n_specialists), 1)
        self._completed = 0
        self._lock = threading.Lock()
        self.stage = "Collecting data"
        self.progress = 0.03

    def on_crew_complete(self) -> None:
        with self._lock:
            self._completed += 1
            c = self._completed
            self.stage, self.progress = self._compute(c)

    def _compute(self, c: int) -> Tuple[str, float]:
        n = self.n
        if c <= 0:
            return "Collecting data", 0.03
        if c == 1:
            return "Running specialist analysis", 0.12
        if c <= 1 + n:  # specialists completing (c-1 of n done)
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


# Register one persistent bus listener (best-effort; mirrors crew/event_listener).
try:  # pragma: no cover - exercised only with crewai installed
    from crewai.utilities.events import crewai_event_bus
    from crewai.utilities.events.crewai_events import CrewKickoffCompleteEvent

    @crewai_event_bus.on(CrewKickoffCompleteEvent)
    def _on_crew_complete(source, event):  # noqa: ANN001
        try:
            _dispatch_crew_complete()
        except Exception as exc:  # never let progress break a run
            _logger.debug("progress dispatch failed: %s", exc)

    _BUS_AVAILABLE = True
except (ImportError, AttributeError):  # pragma: no cover
    _BUS_AVAILABLE = False
