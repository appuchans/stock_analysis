"""Why a piece of data is missing from a run — recorded where it happens.

The analysis stages can only report *that* something was absent; they have no
visibility into whether a key was unset, a provider tier refused the endpoint,
or a request failed. That distinction is the whole difference between "buy a
better plan", "fix your config" and "retry later", so it is captured here at
the point of failure rather than inferred afterwards from LLM prose.

Process-global and reset per run, matching ``token_meter`` and ``llm_budget``
(runs are serialized by the single-worker JobManager, so there is exactly one
active run to attribute entries to).

Output goes to the operator-facing run report and the console log — never to
the client-facing report.
"""

import logging
import threading
from typing import Any, Dict, List

_logger = logging.getLogger(__name__)

_lock = threading.Lock()
_entries: List[Dict[str, Any]] = []

# Why an optional dataset is absent. Ordered roughly by how actionable it is.
NOT_CONFIGURED = "not_configured"  # no API key set
NOT_IN_PLAN = "not_in_plan"  # key valid, endpoint above the tier
NO_DATA = "no_data"  # provider has no such data for this symbol
NOT_APPLICABLE = "not_applicable"  # meaningless for this asset type
FAILED = "failed"  # request errored

_REMEDY = {
    NOT_CONFIGURED: "set the API key in .env",
    NOT_IN_PLAN: "requires a paid tier on this provider",
    NO_DATA: "provider has no data for this symbol",
    NOT_APPLICABLE: "not applicable to this asset type",
    FAILED: "transient — retrying may succeed",
}


def reset() -> None:
    with _lock:
        _entries.clear()


def record(item: str, reason: str, source: str = "", detail: str = "") -> None:
    """Record one missing dataset.

    ``item`` is what the reader would miss (e.g. "revenue segmentation"), not
    the internal method name.
    """
    with _lock:
        _entries.append(
            {
                "item": item,
                "reason": reason,
                "source": source,
                "detail": detail,
                "remedy": _REMEDY.get(reason, ""),
            }
        )


def snapshot() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(e) for e in _entries]


def log_summary(symbol: str) -> None:
    """Emit one consolidated console line per missing dataset.

    At INFO because an absent optional dataset is normal operation, not a
    fault — but it is exactly what an operator greps for when a report looks
    thinner than expected.
    """
    entries = snapshot()
    if not entries:
        _logger.info("[gaps] %s: all configured data sources returned data", symbol)
        return
    _logger.info("[gaps] %s: %d dataset(s) unavailable", symbol, len(entries))
    for e in entries:
        _logger.info(
            "[gaps] %s: %s — %s%s%s",
            symbol,
            e["item"],
            e["reason"],
            f" ({e['source']})" if e["source"] else "",
            f": {e['detail']}" if e["detail"] else "",
        )


def as_markdown() -> str:
    """The diagnostics table for the run report."""
    entries = snapshot()
    if not entries:
        return "All configured data sources returned data for this run."
    lines = [
        "| Missing data | Reason | Source | What to do |",
        "| --- | --- | --- | --- |",
    ]
    for e in entries:
        detail = f" — {e['detail']}" if e["detail"] else ""
        lines.append(
            f"| {e['item']} | {e['reason']}{detail} | {e['source'] or '—'} "
            f"| {e['remedy']} |"
        )
    return "\n".join(lines)
