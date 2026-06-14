"""Free, keyless social-sentiment collection (Stocktwits + Reddit).

Each source degrades independently: a blocked or rate-limited endpoint adds an
entry to ``sources_failed`` instead of failing the whole tool. A top-level
``error`` key is only set when every source fails, so partial results are
cached but total failures are retried (cached_tool skips caching error dicts).
"""

import logging
from datetime import datetime
from typing import Any, Dict

from crewai.tools import BaseTool

from . import _http

from .cache import cached_tool

_logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_REDDIT_UA = "stock-analysis-research-tool/1.0 (educational research)"


def _fetch_stocktwits(symbol: str) -> Dict[str, Any]:
    """Last ~30 Stocktwits messages with explicit Bullish/Bearish labels."""
    resp = _http.get(
        f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json",
        headers={"User-Agent": _BROWSER_UA},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    messages = data.get("messages", []) or []

    # Aggregate counts only — individual message text is intentionally NOT
    # collected: retail chatter is anecdotal and must never be quoted in reports.
    bullish = bearish = unlabeled = 0
    for m in messages:
        label = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        if label == "Bullish":
            bullish += 1
        elif label == "Bearish":
            bearish += 1
        else:
            unlabeled += 1

    labeled = bullish + bearish
    return {
        "messages_sampled": len(messages),
        "bullish": bullish,
        "bearish": bearish,
        "unlabeled": unlabeled,
        "bullish_ratio_pct": round(bullish / labeled * 100, 1) if labeled else None,
        "watchers": (data.get("symbol") or {}).get("watchlist_count"),
    }


def _fetch_reddit_json(symbol: str) -> Dict[str, Any]:
    """Reddit's public JSON search (blocked with 403 on some networks)."""
    resp = _http.get(
        "https://www.reddit.com/r/stocks+wallstreetbets+investing/search.json",
        params={"q": symbol, "restrict_sr": "on", "sort": "new", "t": "week", "limit": 25},
        headers={"User-Agent": _REDDIT_UA},
        timeout=10,
    )
    resp.raise_for_status()
    posts = [c.get("data", {}) for c in resp.json().get("data", {}).get("children", [])]

    # Volume/engagement aggregates only — post titles and bodies are not
    # collected so they can never be quoted in reports.
    return {
        "posts_last_week": len(posts),
        "total_score": sum(int(p.get("score", 0)) for p in posts),
        "total_comments": sum(int(p.get("num_comments", 0)) for p in posts),
        "via": "json",
    }


def _fetch_reddit_rss(symbol: str) -> Dict[str, Any]:
    """Reddit's Atom feed — frequently served where the JSON API returns 403.

    Gives post volume and titles (no scores/comments), which is still a usable
    activity signal.
    """
    resp = _http.get(
        "https://www.reddit.com/r/stocks+wallstreetbets+investing/search.rss",
        params={"q": symbol, "restrict_sr": "on", "sort": "new", "t": "week", "limit": 25},
        headers={"User-Agent": _REDDIT_UA},
        timeout=10,
    )
    resp.raise_for_status()
    entries = resp.text.count("<entry>")
    return {
        "posts_last_week": entries,
        "note": "post volume only — engagement metrics not exposed by the feed",
        "via": "rss",
    }


def _fetch_reddit(symbol: str) -> Dict[str, Any]:
    """Reddit activity with JSON→RSS fallback."""
    try:
        return _fetch_reddit_json(symbol)
    except Exception as exc:
        _logger.info("reddit json blocked (%s); trying RSS", type(exc).__name__)
        return _fetch_reddit_rss(symbol)


def _fetch_market_mood(_symbol: str) -> Dict[str, Any]:
    """CNN Fear & Greed index — keyless, market-wide sentiment context."""
    resp = _http.get(
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        headers={"User-Agent": _BROWSER_UA},
        timeout=10,
    )
    resp.raise_for_status()
    fg = resp.json().get("fear_and_greed", {})
    score = fg.get("score")
    return {
        "fear_greed_score": round(float(score), 1) if score is not None else None,
        "rating": fg.get("rating"),
        "note": "market-wide index (CNN Fear & Greed), not stock-specific",
    }


class SocialSentimentTool(BaseTool):
    """Retail-investor sentiment from free, keyless social sources."""

    name: str = "Social Media Sentiment"
    description: str = (
        "Collects AGGREGATE retail-investor sentiment for a symbol: Stocktwits "
        "bullish/bearish label counts and ratio with watcher count, Reddit post "
        "volume in r/stocks, r/wallstreetbets, r/investing (automatic RSS "
        "fallback), and the market-wide CNN Fear & Greed index. Individual "
        "messages/posts are deliberately not collected — report ratios and "
        "trends, never quotes. Free, no API key."
    )

    @cached_tool(ttl=1800)
    def _run(self, symbol: str) -> Dict[str, Any]:
        symbol = symbol.strip().upper()
        result: Dict[str, Any] = {
            "symbol": symbol,
            "sources_ok": [],
            "sources_failed": [],
            "as_of": datetime.now().isoformat(timespec="minutes"),
        }

        for name, fetcher in (
            ("stocktwits", _fetch_stocktwits),
            ("reddit", _fetch_reddit),
            ("market_mood", _fetch_market_mood),
        ):
            try:
                result[name] = fetcher(symbol)
                result["sources_ok"].append(name)
            except Exception as exc:
                # Technical detail goes to logs only — reports must never contain
                # raw error messages or HTTP status codes.
                _logger.info("%s fetch failed for %s: %s: %s",
                             name, symbol, type(exc).__name__, str(exc)[:120])
                result["sources_failed"].append({
                    "source": name,
                    "note": f"{name} data was unavailable at the time of writing",
                })

        st = result.get("stocktwits") or {}
        labeled = (st.get("bullish") or 0) + (st.get("bearish") or 0)
        if labeled >= 5:
            ratio = st["bullish"] / labeled
            bias = "bullish" if ratio >= 0.6 else ("bearish" if ratio <= 0.4 else "mixed")
        else:
            bias = "insufficient_data"
        result["aggregate"] = {"overall_bias": bias, "labeled_messages": labeled}

        if not result["sources_ok"]:
            # Total failure must not be cached — cached_tool skips error dicts.
            result["error"] = "social sentiment sources unavailable"
            result["fallback_instruction"] = (
                "Social platform data is unavailable. Characterize retail sentiment "
                "qualitatively from news coverage and web search instead, and state "
                "clearly that the assessment is not based on platform metrics."
            )
        return result
