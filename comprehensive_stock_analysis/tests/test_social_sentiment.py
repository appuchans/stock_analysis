"""Network-free tests for the SocialSentimentTool."""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from src.stock_analysis.tools.social_sentiment import SocialSentimentTool


def _stocktwits_response(bullish=8, bearish=2):
    messages = []
    for i in range(bullish):
        messages.append(
            {
                "body": f"to the moon {i}",
                "created_at": "2026-06-11T10:00:00Z",
                "entities": {"sentiment": {"basic": "Bullish"}},
            }
        )
    for i in range(bearish):
        messages.append(
            {
                "body": f"overvalued {i}",
                "created_at": "2026-06-11T11:00:00Z",
                "entities": {"sentiment": {"basic": "Bearish"}},
            }
        )
    messages.append({"body": "no label", "entities": {"sentiment": None}})
    resp = Mock()
    resp.json.return_value = {
        "messages": messages,
        "symbol": {"watchlist_count": 12345},
    }
    resp.raise_for_status = Mock()
    return resp


def _reddit_response(posts=3):
    children = [
        {
            "data": {
                "title": f"Post {i}",
                "subreddit": "stocks",
                "score": 10 * i,
                "num_comments": i,
            }
        }
        for i in range(posts)
    ]
    resp = Mock()
    resp.json.return_value = {"data": {"children": children}}
    resp.raise_for_status = Mock()
    return resp


def _rss_response(entries=4):
    body = (
        "<feed><title>search results</title>"
        + "".join(
            f"<entry><title>RSS Post {i} about NVDA</title></entry>"
            for i in range(entries)
        )
        + "</feed>"
    )
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
        with patch(
            "src.stock_analysis.tools._http.SESSION.get",
            side_effect=self._route(_stocktwits_response(), _reddit_response()),
        ):
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
        with patch(
            "src.stock_analysis.tools._http.SESSION.get",
            side_effect=self._route(
                _stocktwits_response(), blocked, reddit_rss=_rss_response(4)
            ),
        ):
            out = SocialSentimentTool()._run("NVDA")
        assert "reddit" in out["sources_ok"]
        assert out["reddit"]["via"] == "rss"
        assert out["reddit"]["posts_last_week"] == 4
        # Aggregates only — no message/post text may reach the agents
        assert "top_posts" not in out["reddit"]

    def test_reddit_fully_blocked_degrades_gracefully(self, _redis):
        blocked = requests.HTTPError("403 Forbidden")
        with patch(
            "src.stock_analysis.tools._http.SESSION.get",
            side_effect=self._route(
                _stocktwits_response(2, 8), blocked, reddit_rss=blocked
            ),
        ):
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
        with patch("src.stock_analysis.tools._http.SESSION.get", side_effect=boom):
            out = SocialSentimentTool()._run("NVDA")
        assert out["sources_ok"] == []
        assert "error" in out

    def test_no_message_text_reaches_agents(self, _redis):
        """Individual posts are subjective — only aggregates may be collected."""
        with patch(
            "src.stock_analysis.tools._http.SESSION.get",
            side_effect=self._route(_stocktwits_response(), _reddit_response()),
        ):
            out = SocialSentimentTool()._run("NVDA")
        import json

        blob = json.dumps(out)
        assert "sample_messages" not in blob
        assert "top_posts" not in blob
        assert "to the moon" not in blob  # message bodies from the fixture

    def test_small_sample_is_insufficient(self, _redis):
        with patch(
            "src.stock_analysis.tools._http.SESSION.get",
            side_effect=self._route(_stocktwits_response(2, 1), _reddit_response(0)),
        ):
            out = SocialSentimentTool()._run("NVDA")
        assert out["aggregate"]["overall_bias"] == "insufficient_data"


class TestRedditOAuth:
    """Anonymous Reddit search is 403-ed and the RSS fallback carries no
    engagement data, so a free registered app is what restores the numbers the
    sentiment stage needs. It must stay entirely optional."""

    def _clear_token(self):
        from src.stock_analysis.tools import social_sentiment as ss

        ss._reddit_token["value"] = None
        ss._reddit_token["expires_at"] = 0.0

    def test_no_credentials_means_no_token_and_no_request(self, monkeypatch):
        from src.stock_analysis.config import settings as settings_mod
        from src.stock_analysis.tools import social_sentiment as ss

        self._clear_token()
        monkeypatch.setattr(settings_mod.settings, "reddit_client_id", None)
        monkeypatch.setattr(settings_mod.settings, "reddit_client_secret", None)

        def _boom(*a, **k):
            raise AssertionError("must not call Reddit without credentials")

        monkeypatch.setattr(ss._http, "post", _boom)
        assert ss._reddit_oauth_token() is None

    def test_token_is_cached_between_calls(self, monkeypatch):
        """A batch run must not request a fresh token per symbol."""
        from src.stock_analysis.config import settings as settings_mod
        from src.stock_analysis.tools import social_sentiment as ss

        self._clear_token()
        monkeypatch.setattr(settings_mod.settings, "reddit_client_id", "id")
        monkeypatch.setattr(settings_mod.settings, "reddit_client_secret", "secret")
        calls = []

        class _R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"access_token": "tok", "expires_in": 3600}

        monkeypatch.setattr(
            ss._http, "post", lambda *a, **k: (calls.append(1), _R())[1]
        )
        assert ss._reddit_oauth_token() == "tok"
        assert ss._reddit_oauth_token() == "tok"
        assert len(calls) == 1

    def test_oauth_search_returns_engagement_metrics(self, monkeypatch):
        from src.stock_analysis.tools import social_sentiment as ss

        class _R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "data": {
                        "children": [
                            {"data": {"score": 10, "num_comments": 4, "upvote_ratio": 0.9}},
                            {"data": {"score": 20, "num_comments": 6, "upvote_ratio": 0.7}},
                        ]
                    }
                }

        monkeypatch.setattr(ss._http, "get", lambda *a, **k: _R())
        out = ss._fetch_reddit_oauth("AMZN", "tok")
        assert out["posts_last_week"] == 2
        assert out["total_score"] == 30
        assert out["total_comments"] == 10
        assert out["avg_upvote_ratio"] == 0.8
        assert out["via"] == "oauth"

    def test_oauth_failure_falls_through_to_the_anonymous_chain(self, monkeypatch):
        from src.stock_analysis.tools import social_sentiment as ss

        monkeypatch.setattr(ss, "_reddit_oauth_token", lambda: "tok")
        monkeypatch.setattr(
            ss, "_fetch_reddit_oauth",
            lambda *a: (_ for _ in ()).throw(RuntimeError("429")),
        )
        monkeypatch.setattr(ss, "_fetch_reddit_json", lambda s: {"via": "json"})
        assert ss._fetch_reddit("AMZN")["via"] == "json"

    def test_no_post_text_is_ever_collected(self, monkeypatch):
        """Retail chatter must never be quotable in a report."""
        from src.stock_analysis.tools import social_sentiment as ss

        class _R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "data": {
                        "children": [
                            {"data": {"score": 1, "title": "AMZN TO THE MOON",
                                      "selftext": "buy now"}}
                        ]
                    }
                }

        monkeypatch.setattr(ss._http, "get", lambda *a, **k: _R())
        out = ss._fetch_reddit_oauth("AMZN", "tok")
        assert "TO THE MOON" not in str(out)
        assert "buy now" not in str(out)
