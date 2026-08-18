"""Sentiment-scored financial news — Alpha Vantage, with Marketaux as backup.

The keyless news path (``free_data_collection``) scrapes Google/Bing/Yahoo RSS
and yields headlines only, so the sentiment stage has to infer tone from
wording. These providers return news with a *per-ticker* sentiment score
already attached, which is both more reliable and cheaper than asking an LLM to
judge fifty headlines.

Why Alpha Vantage leads: its free tier returns 50 scored articles in one call,
against Marketaux's 3 (the free plan enforces ``limit=3`` regardless of what is
requested). Marketaux is kept as a fallback because it carries the specific
sentence that drove each score, and because the two have different daily
budgets — roughly 25 requests/day for Alpha Vantage, 100 for Marketaux — so one
covers the other when a budget runs out.

Both normalise onto the same shape::

    {"symbol", "articles": [...], "sentiment": {...}, "source"}

with ``sentiment_score`` on a -1..+1 scale so downstream code never has to know
which provider answered.
"""

import logging
from typing import Any, Dict, List, Optional

from .. import _http
from . import base

_logger = logging.getLogger(__name__)

_AV_URL = "https://www.alphavantage.co/query"
_MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"

# Alpha Vantage's documented bands, reused so our label matches theirs.
_BULLISH = 0.15
_BEARISH = -0.15


def _label(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    if score >= 0.35:
        return "bullish"
    if score >= _BULLISH:
        return "somewhat-bullish"
    if score > _BEARISH:
        return "neutral"
    if score > -0.35:
        return "somewhat-bearish"
    return "bearish"


def _summarise(articles: List[Dict[str, Any]], symbol: str) -> Dict[str, Any]:
    """Aggregate per-article scores into one figure for the sentiment stage."""
    scored = [a for a in articles if isinstance(a.get("sentiment_score"), (int, float))]
    if not scored:
        return {}
    # Relevance-weighted: a passing mention of the ticker in a macro piece
    # should not move the average as much as a story about the company.
    weights = [
        a.get("relevance") if isinstance(a.get("relevance"), (int, float)) else 1.0
        for a in scored
    ]
    total_w = sum(weights) or float(len(scored))
    avg = sum(a["sentiment_score"] * w for a, w in zip(scored, weights)) / total_w
    return {
        "symbol": symbol,
        "article_count": len(scored),
        "avg_sentiment_score": round(avg, 4),
        "label": _label(avg),
        "bullish_count": sum(1 for a in scored if a["sentiment_score"] >= _BULLISH),
        "bearish_count": sum(1 for a in scored if a["sentiment_score"] <= _BEARISH),
        "neutral_count": sum(
            1 for a in scored if _BEARISH < a["sentiment_score"] < _BULLISH
        ),
    }


class AlphaVantageNewsProvider(base.ProviderBase):
    name = "alpha_vantage"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def get_news_sentiment(self, symbol: str, limit: int = 50) -> Dict[str, Any]:
        try:
            resp = _http.get(
                _AV_URL,
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": symbol,
                    "limit": limit,
                    "apikey": self._api_key,
                },
                timeout=25,
            )
            resp.raise_for_status()
            payload = resp.json() or {}
            # Alpha Vantage signals quota exhaustion with a 200 and a "Note" or
            # "Information" key rather than an HTTP error — treat as a gap so
            # the router falls through instead of reporting a failure.
            if "feed" not in payload:
                if payload.get("Note") or payload.get("Information"):
                    _logger.info("Alpha Vantage quota/limit reached for %s", symbol)
                return {}

            articles: List[Dict[str, Any]] = []
            for row in payload.get("feed") or []:
                mine = next(
                    (
                        t
                        for t in (row.get("ticker_sentiment") or [])
                        if (t.get("ticker") or "").upper() == symbol.upper()
                    ),
                    None,
                )
                if mine is None:
                    continue

                def _f(v: Any) -> Optional[float]:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None

                ts = row.get("time_published") or ""
                articles.append(
                    {
                        "headline": row.get("title"),
                        "summary": (row.get("summary") or "")[:400],
                        "source": row.get("source"),
                        "url": row.get("url"),
                        # AV timestamps are 20260814T093000.
                        "published_at": (
                            f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}T{ts[9:11]}:{ts[11:13]}"
                            if len(ts) >= 13
                            else None
                        ),
                        "sentiment_score": _f(mine.get("ticker_sentiment_score")),
                        "sentiment_label": mine.get("ticker_sentiment_label"),
                        "relevance": _f(mine.get("relevance_score")),
                    }
                )
            if not articles:
                return {}
            articles.sort(key=lambda a: a.get("relevance") or 0, reverse=True)
            return {
                "symbol": symbol,
                "articles": articles[:25],
                "sentiment": _summarise(articles, symbol),
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning(
                "Alpha Vantage get_news_sentiment failed for %s: %s", symbol, exc
            )
            return {"error": str(exc)}


class MarketauxNewsProvider(base.ProviderBase):
    name = "marketaux"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def get_news_sentiment(self, symbol: str, limit: int = 50) -> Dict[str, Any]:
        try:
            resp = _http.get(
                _MARKETAUX_URL,
                params={
                    "symbols": symbol,
                    "filter_entities": "true",
                    "language": "en",
                    "limit": limit,
                    "api_token": self._api_key,
                },
                timeout=25,
            )
            resp.raise_for_status()
            rows = (resp.json() or {}).get("data") or []
            if not rows:
                return {}

            articles: List[Dict[str, Any]] = []
            for row in rows:
                entity = next(
                    (
                        e
                        for e in (row.get("entities") or [])
                        if (e.get("symbol") or "").upper() == symbol.upper()
                    ),
                    None,
                )
                if entity is None:
                    continue
                score = entity.get("sentiment_score")
                highlights = entity.get("highlights") or []
                articles.append(
                    {
                        "headline": row.get("title"),
                        "summary": (row.get("description") or row.get("snippet") or "")[
                            :400
                        ],
                        "source": row.get("source"),
                        "url": row.get("url"),
                        "published_at": row.get("published_at"),
                        "sentiment_score": (
                            float(score) if isinstance(score, (int, float)) else None
                        ),
                        "sentiment_label": _label(
                            float(score) if isinstance(score, (int, float)) else None
                        ),
                        # Marketaux's match_score is an absolute relevance
                        # measure, not 0..1 — normalise so the weighted average
                        # in _summarise stays comparable across providers.
                        "relevance": (
                            min(float(entity["match_score"]) / 10.0, 1.0)
                            if isinstance(entity.get("match_score"), (int, float))
                            else None
                        ),
                        # The sentence that drove the score — useful context an
                        # aggregate number cannot convey.
                        "highlight": (
                            highlights[0].get("highlight") if highlights else None
                        ),
                    }
                )
            if not articles:
                return {}
            return {
                "symbol": symbol,
                "articles": articles,
                "sentiment": _summarise(articles, symbol),
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning(
                "Marketaux get_news_sentiment failed for %s: %s", symbol, exc
            )
            return {"error": str(exc)}
