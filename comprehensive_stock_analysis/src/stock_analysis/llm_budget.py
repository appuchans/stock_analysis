"""Hard LLM-call budget — the last line of defense against runaway loops.

Every LLM request in the app flows through ``BudgetedLLM`` (built by
``BaseAgent``), which calls :func:`check_and_increment` *before* any network
request is made. Once the per-run budget is exhausted, every further attempt
raises :class:`LLMBudgetExceededError` immediately — zero additional API spend
is physically possible, no matter what an agent, retry layer, or framework bug
does.

Budget is configured via ``MAX_LLM_CALLS_PER_RUN`` (settings, default 300 —
roughly 2x a worst-case legitimate deep run). Crews call :func:`reset` at the
start of each analysis; batch runs scale the allowance by symbol count.
"""

import logging
import threading

_logger = logging.getLogger(__name__)

_lock = threading.Lock()
_count = 0
_limit: int = 0  # resolved lazily from settings on first use
_warned = False
_aborted = False


class LLMBudgetExceededError(RuntimeError):
    """Raised before an LLM request when the per-run call budget is exhausted."""


class AnalysisAbortedError(RuntimeError):
    """Raised at the next LLM call after a user requests cancellation."""


def request_abort() -> None:
    """Ask the running analysis to stop — the next LLM call raises and unwinds
    the flow. Cooperative (a blocking call in flight finishes first)."""
    global _aborted
    with _lock:
        _aborted = True
    _logger.info("[llm-budget] abort requested — run will stop at next LLM call")


def _resolve_limit() -> int:
    global _limit
    if _limit <= 0:
        from .config.settings import settings
        _limit = settings.max_llm_calls_per_run
    return _limit


def reset(allowance_multiplier: int = 1) -> None:
    """Start a new budget window (call at the beginning of each analysis run)."""
    global _count, _limit, _warned, _aborted
    from .config.settings import settings
    with _lock:
        _count = 0
        _warned = False
        _aborted = False
        _limit = settings.max_llm_calls_per_run * max(1, allowance_multiplier)
    _logger.info("[llm-budget] reset — limit=%d calls", _limit)


def check_and_increment() -> None:
    """Account for one LLM call; raise when the budget is exhausted or aborted.

    Note: the increment happens *before* the actual network request, so failed
    calls (network errors, timeouts) still consume one budget unit. Under high
    retry conditions this may exhaust the budget faster than expected. Raise
    MAX_LLM_CALLS_PER_RUN if legitimate runs hit the limit.
    """
    global _count, _warned
    with _lock:
        if _aborted:
            raise AnalysisAbortedError("analysis aborted by user")
        limit = _resolve_limit()
        _count += 1
        count = _count
    if count > limit:
        raise LLMBudgetExceededError(
            f"LLM call budget exhausted ({limit} calls this run). This is a "
            f"safety stop against runaway agent loops — no further API calls "
            f"will be made. If this run is legitimately large, raise "
            f"MAX_LLM_CALLS_PER_RUN."
        )
    if not _warned and count > limit * 0.8:
        _warned = True
        _logger.warning(
            "[llm-budget] %d of %d LLM calls used (80%% threshold) — "
            "a possible loop will be stopped at the limit", count, limit,
        )


def used() -> int:
    with _lock:
        return _count
