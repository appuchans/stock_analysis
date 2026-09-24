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
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)
_lock = threading.Lock()

_FIELDS = ("total_tokens", "prompt_tokens", "completion_tokens", "cached_prompt_tokens")
_totals: Dict[str, int] = {f: 0 for f in _FIELDS}
_requests = 0
# Per workload-category buckets (extraction/quantitative/narrative/synthesis),
# so a run reports what each model class cost — the measurement behind the
# cheap-flash-vs-strong-synthesis tradeoff. Keys appear only for categories
# that actually ran.
_by_category: Dict[str, Dict[str, int]] = {}


def reset() -> None:
    """Start a fresh accounting window (call at the start of each analysis)."""
    global _requests
    with _lock:
        for f in _FIELDS:
            _totals[f] = 0
        _requests = 0
        _by_category.clear()


def add(usage: Any, category: Optional[str] = None) -> None:
    """Accumulate one crew's ``usage_metrics`` (a UsageMetrics or None).

    ``category`` attributes the crew to a workload class; the caller's
    llm_config category (not the model string) so a mid-run model swap does
    not split one class across two buckets.
    """
    if usage is None:
        return
    global _requests
    with _lock:
        delta = {}
        for f in _FIELDS:
            val = getattr(usage, f, 0) or 0
            try:
                delta[f] = int(val)
            except (TypeError, ValueError):
                delta[f] = 0
        req = int(getattr(usage, "successful_requests", 0) or 0)
        for f in _FIELDS:
            _totals[f] += delta[f]
        _requests += req
        if category:
            bucket = _by_category.setdefault(
                category, {f: 0 for f in _FIELDS} | {"successful_requests": 0}
            )
            for f in _FIELDS:
                bucket[f] += delta[f]
            bucket["successful_requests"] += req


def snapshot() -> Dict[str, Any]:
    """Current run totals as a plain dict (plus per-category buckets)."""
    with _lock:
        snap = dict(_totals)
        snap["successful_requests"] = _requests
        snap["by_category"] = {cat: dict(vals) for cat, vals in _by_category.items()}
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
                total,
                threshold,
            )
