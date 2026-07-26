"""Per-run tool invocation telemetry, aggregated across all crews in a flow.

Tracks call counts, error counts, cache hits, and latency per tool name.
Thread-safe because analysis stages run concurrently. Used for visibility
into tool behavior and LLM loop health (tool cache hit rate, errors).
"""

import logging
import threading
from typing import Any, Dict

_logger = logging.getLogger(__name__)
_lock = threading.Lock()

_tools: Dict[str, Dict[str, Any]] = {}


def reset() -> None:
    """Start a fresh telemetry window (call at the start of each analysis)."""
    global _tools
    with _lock:
        _tools = {}


def record_tool_start(tool_name: str) -> None:
    """Record a tool invocation start (for latency tracking)."""
    with _lock:
        if tool_name not in _tools:
            _tools[tool_name] = {
                "calls": 0,
                "errors": 0,
                "cache_hits": 0,
                "total_duration_ms": 0,
            }


def record_tool_finish(
    tool_name: str,
    duration_ms: float,
    from_cache: bool = False,
) -> None:
    """Record a tool invocation finish (success case)."""
    with _lock:
        if tool_name not in _tools:
            _tools[tool_name] = {
                "calls": 0,
                "errors": 0,
                "cache_hits": 0,
                "total_duration_ms": 0,
            }
        _tools[tool_name]["calls"] += 1
        _tools[tool_name]["total_duration_ms"] += duration_ms
        if from_cache:
            _tools[tool_name]["cache_hits"] += 1


def record_tool_error(tool_name: str) -> None:
    """Record a tool invocation error."""
    with _lock:
        if tool_name not in _tools:
            _tools[tool_name] = {
                "calls": 0,
                "errors": 0,
                "cache_hits": 0,
                "total_duration_ms": 0,
            }
        _tools[tool_name]["errors"] += 1


def snapshot() -> Dict[str, Dict[str, Any]]:
    """Current run telemetry as a plain dict keyed by tool name."""
    with _lock:
        return {k: dict(v) for k, v in _tools.items()}
