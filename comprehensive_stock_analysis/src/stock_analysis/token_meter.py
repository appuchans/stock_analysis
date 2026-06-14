"""Per-run token accounting, aggregated across every crew in a flow.

The flow runs many small crews (`_run_crew`); each exposes a CrewAI
``usage_metrics`` object that is otherwise discarded. This module accumulates
them so a run reports real token totals (used for the spend alert and the
end-of-run summary). Thread-safe because analysis stages run concurrently.

This is observability only — the hard runaway guard is `llm_budget` (call
count). Tokens drive the *quota alert*; calls drive the *safety stop*.
"""

import logging
import threading
from typing import Any, Dict

_logger = logging.getLogger(__name__)
_lock = threading.Lock()

_FIELDS = ("total_tokens", "prompt_tokens", "completion_tokens", "cached_prompt_tokens")
_totals: Dict[str, int] = {f: 0 for f in _FIELDS}
_requests = 0


def reset() -> None:
    """Start a fresh accounting window (call at the start of each analysis)."""
    global _requests
    with _lock:
        for f in _FIELDS:
            _totals[f] = 0
        _requests = 0


def add(usage: Any) -> None:
    """Accumulate one crew's ``usage_metrics`` (a UsageMetrics or None)."""
    if usage is None:
        return
    global _requests
    with _lock:
        for f in _FIELDS:
            val = getattr(usage, f, 0) or 0
            try:
                _totals[f] += int(val)
            except (TypeError, ValueError):
                pass
        _requests += int(getattr(usage, "successful_requests", 0) or 0)


def snapshot() -> Dict[str, int]:
    """Current run totals as a plain dict."""
    with _lock:
        snap = dict(_totals)
        snap["successful_requests"] = _requests
        return snap


def check_alert() -> None:
    """Log a WARNING once the run's token total crosses the configured alert.

    Disabled when ``LLM_TOKEN_ALERT`` is 0 (the default). Provider-agnostic —
    we alert on tokens rather than a hard-coded price table that goes stale.
    """
    from .config.settings import settings

    threshold = settings.llm_token_alert
    if threshold and threshold > 0:
        total = snapshot()["total_tokens"]
        if total > threshold:
            _logger.warning(
                "[token-alert] run used %d tokens, over the %d alert threshold "
                "(LLM_TOKEN_ALERT) — check for an unexpectedly expensive run",
                total, threshold,
            )
