"""Derive the Overview's two-sentence summary from an *existing* report.

The advisor fills `summary` on every new run, but reports produced before that
field existed have none — and re-running a full analysis to obtain two
sentences costs ~11 LLM calls and >100k tokens for information the finished
recommendation already contains.

This does it with **one** call over the artifacts already on disk: no data
fetch, no crew, no flow. The prompt lives in ``flow_tasks.yaml`` with every
other prompt.

Best-effort throughout: a failure leaves the file untouched and the Overview
falls back to its generated sentences.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from ..config.loader import config_loader
from . import _paths

_logger = logging.getLogger(__name__)

# The brief is "no more than 50 words". Models overshoot it, so enforce rather
# than ask: a little slack, then a retry that quotes the actual count back.
_MAX_WORDS = 55
_MAX_CHARS = 600


def _truncate(value: Any, limit: int) -> str:
    text = json.dumps(value) if isinstance(value, (list, dict)) else str(value or "")
    return text[:limit]


def _performance_facts(symbol: str) -> str:
    """Concrete price performance and headlines from the chart data on disk.

    Without these the model has only the memo's prose to work from, and writes
    something true but vague ("has not kept up with the optimism…"). The target
    is "up solidly this year but stumbled after a Q2 miss" — which needs actual
    numbers and the actual news, not more reasoning.
    """
    chart = {}
    path = _paths.chart_path(symbol)
    try:
        if path is not None and path.exists():
            chart = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return ""

    lines = []
    closes = [
        p.get("close")
        for p in (chart.get("price_history") or [])
        if isinstance(p, dict) and isinstance(p.get("close"), (int, float))
    ]
    price = (chart.get("key_stats") or {}).get("current_price")
    if closes and isinstance(price, (int, float)):

        def pct(n):
            base = closes[max(0, len(closes) - 1 - n)]
            return round((price - base) / base * 100, 1) if base else None

        parts = []
        for label, n in (("1 month", 4), ("6 months", 26), ("12 months", 52)):
            if len(closes) > n:
                v = pct(n)
                if v is not None:
                    parts.append(f"{label}: {v:+.1f}%")
        if parts:
            lines.append("Price change — " + "; ".join(parts))

        stats = chart.get("key_stats") or {}
        hi, lo = stats.get("high_52w"), stats.get("low_52w")
        if hi and lo:
            lines.append(
                f"Now {round((price - hi) / hi * 100, 1):+.1f}% vs its 52-week "
                f"high and {round((price - lo) / lo * 100, 1):+.1f}% vs its low"
            )

    bench = (chart.get("benchmark") or {}).get("history") or []
    bcloses = [
        p.get("close")
        for p in bench
        if isinstance(p, dict) and isinstance(p.get("close"), (int, float))
    ]
    if len(bcloses) > 26:
        base = bcloses[len(bcloses) - 1 - 26]
        if base:
            name = (chart.get("benchmark") or {}).get("symbol") or "the market"
            lines.append(
                f"{name} over the same six months: "
                f"{round((bcloses[-1] - base) / base * 100, 1):+.1f}%"
            )

    headlines = [n.get("title") for n in (chart.get("news") or []) if n.get("title")]
    if headlines:
        lines.append("Recent headlines: " + " | ".join(headlines[:5]))

    cat = chart.get("catalysts") or {}
    if cat.get("next_earnings_date"):
        lines.append(f"Next earnings: {cat['next_earnings_date']}")
    return "\n".join(lines)


def _build_prompt(symbol: str, rec: Dict[str, Any]) -> str:
    task = config_loader.load_flow_tasks_config().get("recommendation_summary") or {}
    description = task.get("description") or ""
    return description.format(
        symbol=symbol,
        recommendation=rec.get("recommendation") or "not stated",
        performance=_performance_facts(symbol) or "not available",
        # Bounded so a long memo can't blow up a call meant to be cheap.
        reasoning=_truncate(rec.get("reasoning"), 4000),
        key_factors=_truncate(rec.get("key_factors"), 1500),
        risks=_truncate(rec.get("risks"), 1000),
        opportunities=_truncate(rec.get("opportunities"), 1000),
    )


def _clean(text: str) -> str:
    """Strip the wrapping models add despite being told not to."""
    out = (text or "").strip()
    if out.startswith("```"):
        out = out.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    if len(out) >= 2 and out[0] in "\"“'" and out[-1] in "\"”'":
        out = out[1:-1].strip()
    return out


def _price_position(symbol: str) -> Optional[Dict[str, float]]:
    """Current price against its 52-week range, for fact-checking the text."""
    path = _paths.chart_path(symbol)
    try:
        if path is None or not path.exists():
            return None
        stats = (json.loads(path.read_text(encoding="utf-8")) or {}).get(
            "key_stats"
        ) or {}
    except (OSError, ValueError):
        return None
    price, hi, lo = (
        stats.get("current_price"),
        stats.get("high_52w"),
        stats.get("low_52w"),
    )
    if not all(isinstance(v, (int, float)) and v for v in (price, hi, lo)) or hi <= lo:
        return None
    return {
        "price": float(price),
        "off_high_pct": (float(price) - float(hi)) / float(hi) * 100,
        "off_low_pct": (float(price) - float(lo)) / float(lo) * 100,
        "range_pos": (float(price) - float(lo)) / (float(hi) - float(lo)),
    }


# Claims about where the price sits are the ones a model will confidently
# invent — a first attempt asserted IBM was "near its recent high" while it sat
# 28% below it. These are cheap to check against the numbers, so check them.
_NEAR_HIGH = re.compile(
    r"\b(near(ing)?|close to|at|around)\b[^.]{0,40}\b(record|all[- ]time|52[- ]week|recent|its)?\s*high",
    re.I,
)
_NEAR_LOW = re.compile(
    r"\b(near(ing)?|close to|at|around)\b[^.]{0,40}\b(record|all[- ]time|52[- ]week|recent|its)?\s*low",
    re.I,
)


def _too_long(text: str) -> Optional[str]:
    words = len(text.split())
    return (
        f"runs to {words} words, over the 50-word limit" if words > _MAX_WORDS else None
    )


def _contradicts_data(text: str, symbol: str) -> Optional[str]:
    """Return a reason when the text conflicts with the price data, else None."""
    over = _too_long(text)
    if over:
        return over
    pos = _price_position(symbol)
    if pos is None:
        return None
    if _NEAR_HIGH.search(text) and pos["range_pos"] < 0.85:
        return (
            f"claims the price is near its high while it sits "
            f"{pos['off_high_pct']:.0f}% below the 52-week high"
        )
    if _NEAR_LOW.search(text) and pos["range_pos"] > 0.15:
        return (
            f"claims the price is near its low while it sits "
            f"{pos['off_low_pct']:+.0f}% above the 52-week low"
        )
    return None


def generate_summary(symbol: str, rec: Dict[str, Any]) -> Optional[str]:
    """One LLM call turning a finished recommendation into two sentences.

    Retried once if the result contradicts the price data — cheaper than
    shipping a confidently wrong sentence at the top of a report.
    """
    prompt = _build_prompt(symbol, rec)
    if not prompt.strip():
        return None
    # Built through BaseAgent so the same provider/model/budget resolution and
    # the per-run LLM cap apply as everywhere else.
    from ..agents.investment_advisor_agent import InvestmentAdvisorAgent

    llm = InvestmentAdvisorAgent()._build_llm()
    attempt_prompt = prompt
    for attempt in (1, 2):
        text = _clean(str(llm.call(attempt_prompt)))
        if not text or len(text) > _MAX_CHARS:
            _logger.warning(
                "summary for %s rejected (%d chars)", symbol, len(text or "")
            )
            return None
        problem = _contradicts_data(text, symbol)
        if problem is None:
            return text
        _logger.warning(
            "summary for %s %s — %s",
            symbol,
            problem,
            "retrying" if attempt == 1 else "discarding",
        )
        attempt_prompt = (
            prompt + f"\n\nYour previous attempt was factually wrong: it {problem}. "
            "Re-read the price data above and describe the move accurately."
        )
    return None


def ensure_summary(symbol: str, force: bool = False) -> Optional[str]:
    """Add `summary` to a symbol's recommendation file if it lacks one.

    Returns the summary (existing or new), or None when there is nothing to
    work from. Writes back in place so the next page load picks it up.
    """
    path = _paths.recommendation_path(symbol)
    if path is None or not path.exists():
        return None
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("cannot read recommendation for %s: %s", symbol, exc)
        return None
    if not isinstance(rec, dict):
        return None

    existing = (rec.get("summary") or "").strip()
    if existing and not force:
        return existing

    try:
        summary = generate_summary(symbol, rec)
    except Exception as exc:  # never let a backfill break a request
        _logger.warning("summary generation failed for %s: %s", symbol, exc)
        return existing or None
    if not summary:
        return existing or None

    rec["summary"] = summary
    try:
        path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    except OSError as exc:
        _logger.warning("could not persist summary for %s: %s", symbol, exc)
    _logger.info("[summary] backfilled %s from the existing report", symbol)
    return summary
