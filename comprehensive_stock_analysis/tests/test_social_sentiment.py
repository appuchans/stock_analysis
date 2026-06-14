"""Network-free tests for the SocialSentimentTool."""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from src.stock_analysis.tools.social_sentiment import SocialSentimentTool


def _stocktwits_response(bullish=8, bearish=2):
    messages = []
    for i in range(bullish):
        messages.append({"body": f"to the moon {i}", "created_at": "2026-06-11T10:00:00Z",
                         "entities": {"sentiment": {"basic": "Bullish"}}})
    for i in range(bearish):
        messages.append({"body": f"overvalued {i}", "created_at": "2026-06-11T11:00:00Z",
                         "entities": {"sentiment": {"basic": "Bearish"}}})
    messages.append({"body": "no label", "entities": {"sentiment": None}})
    resp = Mock()
    resp.json.return_value = {"messages": messages, "symbol": {"watchlist_count": 12345}}
    resp.raise_for_status = Mock()
    return resp


def _reddit_response(posts=3):
    children = [
        {"data": {"title": f"Post {i}", "subreddit": "stocks", "score": 10 * i,
                  "num_comments": i}}
        for i in range(posts)
    ]
    resp = Mock()
    resp.json.return_value = {"data": {"children": children}}
    resp.raise_for_status = Mock()
    return resp


def _rss_response(entries=4):
    body = "<feed><title>search results</title>" + "".join(
        f"<entry><title>RSS Post {i} about NVDA</title></entry>" for i in range(entries)
    ) + "</feed>"
    resp = Mock()
    resp.text = body
    resp.raise_for_status = Mock()
    return resp


def _mood_response(score=33.7, rating="fear"):
    resp = Mock()
    resp.json.return_value = {"fear_and_greed": {"score": score, "rating": rating}}
    resp.raise_for_status = Mock()
    return resp


@patch("src.stock_analysis.tools.cache._get_redis", return_value=None)
class TestSocialSentimentTool:
    def _route(self, stocktwits, reddit_json, reddit_rss=None, mood=None):
        mood = mood or _mood_response()

        def _get(url, **kwargs):
            if "stocktwits" in url:
                if isinstance(stocktwits, Exception):
                    raise stocktwits
                return stocktwits
            if "search.rss" in url:
                if isinstance(reddit_rss, Exception) or reddit_rss is None:
                    raise reddit_rss or requests.HTTPError("403")
                return reddit_rss
            if "reddit" in url:
                if isinstance(reddit_json, Exception):
                    raise reddit_json
                return reddit_json
            if "fearandgreed" in url:
                if isinstance(mood, Exception):
                    raise mood
                return mood
            raise AssertionError(f"unexpected url {url}")
        return _get

    def test_all_sources_ok(self, _redis):
        with patch("src.stock_analysis.tools._http.SESSION.get",
                   side_effect=self._route(_stocktwits_response(), _reddit_response())):
            out = SocialSentimentTool()._run("NVDA")
        assert out["sources_ok"] == ["stocktwits", "reddit", "market_mood"]
        assert out["stocktwits"]["bullish"] == 8
        assert out["stocktwits"]["bullish_ratio_pct"] == 80.0
        assert out["reddit"]["posts_last_week"] == 3
        assert out["reddit"]["via"] == "json"
        assert out["market_mood"]["fear_greed_score"] == 33.7
        assert out["aggregate"]["overall_bias"] == "bullish"
        assert "error" not in out

    def test_reddit_json_blocked_falls_back_to_rss(self, _redis):
        blocked = requests.HTTPError("403 Forbidden")
        with patch("src.stock_analysis.tools._http.SESSION.get",
                   side_effect=self._route(_stocktwits_response(), blocked,
                                           reddit_rss=_rss_response(4))):
            out = SocialSentimentTool()._run("NVDA")
        assert "reddit" in out["sources_ok"]
        assert out["reddit"]["via"] == "rss"
        assert out["reddit"]["posts_last_week"] == 4
        # Aggregates only — no message/post text may reach the agents
        assert "top_posts" not in out["reddit"]

    def test_reddit_fully_blocked_degrades_gracefully(self, _redis):
        blocked = requests.HTTPError("403 Forbidden")
        with patch("src.stock_analysis.tools._http.SESSION.get",
                   side_effect=self._route(_stocktwits_response(2, 8), blocked,
                                           reddit_rss=blocked)):
            out = SocialSentimentTool()._run("NVDA")
        assert out["sources_ok"] == ["stocktwits", "market_mood"]
        assert any(f["source"] == "reddit" for f in out["sources_failed"])
        # Neutral language only — never raw error text
        for f in out["sources_failed"]:
            assert "403" not in f["note"] and "Forbidden" not in f["note"]
        assert out["aggregate"]["overall_bias"] == "bearish"
        assert "error" not in out  # partial results must remain cacheable

    def test_total_failure_sets_error_so_not_cached(self, _redis):
        boom = requests.ConnectionError("offline")
        with patch("src.stock_analysis.tools._http.SESSION.get",
                   side_effect=boom):
            out = SocialSentimentTool()._run("NVDA")
        assert out["sources_ok"] == []
        assert "error" in out

    def test_no_message_text_reaches_agents(self, _redis):
        """Individual posts are subjective — only aggregates may be collected."""
        with patch("src.stock_analysis.tools._http.SESSION.get",
                   side_effect=self._route(_stocktwits_response(), _reddit_response())):
            out = SocialSentimentTool()._run("NVDA")
        import json
        blob = json.dumps(out)
        assert "sample_messages" not in blob
        assert "top_posts" not in blob
        assert "to the moon" not in blob  # message bodies from the fixture

    def test_small_sample_is_insufficient(self, _redis):
        with patch("src.stock_analysis.tools._http.SESSION.get",
                   side_effect=self._route(_stocktwits_response(2, 1), _reddit_response(0))):
            out = SocialSentimentTool()._run("NVDA")
        assert out["aggregate"]["overall_bias"] == "insufficient_data"
