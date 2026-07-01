"""Tests for free data collection tools in free_data_collection.py."""

import pytest
import json
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime
from src.stock_analysis.tools.free_data_collection import (
    FreeEconomicDataTool,
    FreeCompetitorAnalysisTool,
    FreeIndustryAnalysisTool,
    FreeSECFilingTool,
    YahooFinanceTool,
    FreeFREDTool,
    FreeNewsTool,
    FreeWebSearchTool
)

class TestFreeEconomicDataTool:
    """Tests for FreeEconomicDataTool."""

    @pytest.fixture(autouse=True)
    def _mock_market_proxies(self, monkeypatch):
        """Keep the market-proxy fallback (yfinance) off the network."""
        import pandas as pd

        hist = pd.DataFrame({"Close": [100.0, 105.0]},
                            index=pd.date_range("2026-05-12", periods=2))

        class _T:
            def __init__(self, sym): pass
            def history(self, period="1mo"): return hist

        import src.stock_analysis.tools.free_data_collection as fdc
        monkeypatch.setattr(fdc.yf, "Ticker", _T)

    @patch('src.stock_analysis.tools._http.SESSION.get')
    def test_market_proxies_present_alongside_fred(self, mock_get):
        mock_resp = Mock()
        mock_resp.json.return_value = {"observations": [{"date": "2024-01-01", "value": "5.0"}]}
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp
        tool = FreeEconomicDataTool(fred_api_key="test_key")
        result = tool._run(country="US", indicators='["UNRATE"]')
        assert "market_indicators" in result
        mi = result["market_indicators"]
        assert mi["vix_volatility_index"]["latest"] == 105.0
        assert mi["vix_volatility_index"]["change_1m_pct"] == 5.0

    @patch('src.stock_analysis.tools._http.SESSION.get', side_effect=ConnectionError("FRED down"))
    def test_fred_failure_falls_back_to_market_proxies(self, mock_get):
        tool = FreeEconomicDataTool(fred_api_key="test_key")
        result = tool._run(country="US")
        assert "error" not in result
        assert result["market_indicators"]
        assert "note" in result or result.get("economic_data") is not None

    @patch('src.stock_analysis.tools._http.SESSION.get')
    def test_economic_data_tool_default_indicators(self, mock_get):
        """Test default indicator fetching with mock responses."""
        # Create standard responses for FRED series and info
        mock_obs_response = Mock()
        mock_obs_response.json.return_value = {
            "observations": [
                {"date": "2024-01-01", "value": "100.0"},
                {"date": "2024-02-01", "value": "101.0"},
                {"date": "2024-03-01", "value": "102.0"},
                {"date": "2024-04-01", "value": "103.0"},
                {"date": "2024-05-01", "value": "104.0"},
                {"date": "2024-06-01", "value": "105.0"},
                {"date": "2024-07-01", "value": "106.0"},
                {"date": "2024-08-01", "value": "107.0"},
                {"date": "2024-09-01", "value": "108.0"},
                {"date": "2024-10-01", "value": "109.0"},
                {"date": "2024-11-01", "value": "110.0"},
                {"date": "2024-12-01", "value": "111.0"},
            ]
        }
        mock_obs_response.raise_for_status = Mock()

        mock_info_response = Mock()
        mock_info_response.json.return_value = {
            "seriess": [{"id": "TEST", "title": "Test Series"}]
        }
        mock_info_response.raise_for_status = Mock()

        # Alternate between observation data and series info response
        mock_get.side_effect = lambda url, params=None, **kwargs: (
            mock_obs_response if "observations" in url else mock_info_response
        )

        tool = FreeEconomicDataTool(fred_api_key="test_key")
        result = tool._run(country="US")

        assert "economic_data" in result
        assert "indicator_summaries" in result
        
        # Verify summaries are calculated
        summaries = result["indicator_summaries"]
        assert "GDPC1_real_gdp" in summaries
        assert "CPIAUCSL_inflation" in summaries
        assert "FEDFUNDS_rate" in summaries
        assert "UNRATE_unemployment" in summaries

        assert summaries["GDPC1_real_gdp"]["latest"] == 111.0
        assert summaries["GDPC1_real_gdp"]["trend"] in ("rising", "falling", "stable", "unknown")

    @patch('src.stock_analysis.tools._http.SESSION.get')
    def test_economic_data_tool_custom_indicators(self, mock_get):
        """Test with custom indicators specified as list or JSON string."""
        mock_obs_response = Mock()
        mock_obs_response.json.return_value = {"observations": [{"date": "2024-01-01", "value": "5.0"}]}
        mock_obs_response.raise_for_status = Mock()
        mock_info_response = Mock()
        mock_info_response.json.return_value = {"seriess": []}
        mock_info_response.raise_for_status = Mock()

        mock_get.side_effect = lambda url, params=None, **kwargs: (
            mock_obs_response if "observations" in url else mock_info_response
        )

        tool = FreeEconomicDataTool(fred_api_key="test_key")
        # Run with string list
        result = tool._run(country="US", indicators='["UNRATE"]')
        assert "economic_data" in result
        assert mock_get.call_count > 0


class TestFreeFREDTool:
    """FreeFREDTool must never leak the API key or request URL in error text."""

    @patch("src.stock_analysis.tools.cache._get_redis", return_value=None)
    @patch("src.stock_analysis.tools._http.SESSION.get")
    def test_http_error_does_not_leak_api_key_or_url(self, mock_get, _redis):
        import requests

        secret_key = "supersecretfredkey123"
        tool = FreeFREDTool(api_key=secret_key)

        def _raise_http_error():
            # Mimic requests' real HTTPError message, which embeds the full
            # request URL — including api_key=<key> — in str(exc).
            err = requests.exceptions.HTTPError(
                "429 Client Error: Too Many Requests for url: "
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id=GDP&api_key={secret_key}&file_type=json"
            )
            err.response = Mock(status_code=429)
            raise err

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock(side_effect=_raise_http_error)
        mock_get.return_value = mock_resp

        result = tool._run(series_id="GDP")

        assert "error" in result
        assert secret_key not in result["error"]
        assert "api_key=" not in result["error"]
        assert "429" in result["error"] or "HTTP" in result["error"]


class TestFreeCompetitorAnalysisTool:
    """Tests for FreeCompetitorAnalysisTool."""

    @patch('src.stock_analysis.tools.free_data_collection.YahooFinanceTool')
    @patch('src.stock_analysis.tools.free_data_collection.FreeWebSearchTool')
    def test_competitor_analysis_filtering_and_parallel_validation(self, mock_search_class, mock_yahoo_class):
        """Test candidate extraction, stop-word blocklisting, limit, and validation."""
        # Setup YahooFinanceTool mock
        mock_yahoo_instance = Mock()
        mock_yahoo_class.return_value = mock_yahoo_instance

        # Primary company info
        mock_yahoo_instance._run.side_effect = lambda symbol, **kwargs: (
            {
                "company_info": {"name": "Test Main Corp", "sector": "Tech", "industry": "Software"},
                "market_data": {"market_cap": 1000000, "current_price": 50.0}
            } if symbol == "AAPL" else {
                "company_info": {"name": f"Competitor {symbol}", "sector": "Tech", "industry": "Software"},
                "market_data": {"market_cap": 500000, "current_price": 40.0}
            }
        )

        # Setup FreeWebSearchTool mock
        mock_search_instance = Mock()
        mock_search_class.return_value = mock_search_instance
        # Text containing:
        # - Target symbol AAPL (should be filtered out)
        # - Stop words: AND, NYSE, SEC, ETF (should be filtered out)
        # - Tickers to validate: MSFT, GOOG, AMZN, META, NFLX, TSLA, NVDA, ORCL, IBM, CSCO (10 tickers)
        mock_search_instance._run.return_value = {
            "results": [
                {
                    "title": "Top Competitors are MSFT and GOOG on NYSE",
                    "snippet": "We also check AMZN, META, ETF, SEC, and NFLX."
                },
                {
                    "title": "TSLA and NVDA compete in tech space",
                    "snippet": "Other potential names include ORCL, IBM, CSCO, and CEO AAPL."
                }
            ]
        }

        tool = FreeCompetitorAnalysisTool()
        result = tool._run("AAPL", industry="Software")

        assert "competitors" in result
        assert result["industry"] == "Software"
        assert result["sector"] == "Tech"

        # Check candidate extraction and limits (max 8 candidates checked)
        # MSFT, GOOG, AMZN, META, NFLX, TSLA, NVDA, ORCL, IBM, CSCO -> 10 valid tickers.
        # It should deduplicate and limit validation to at most 8 candidates.
        # Let's count YahooFinanceTool._run calls for symbols other than AAPL.
        # The tool now calls yahoo_tool._run(symbol=symbol) with symbol as a
        # keyword argument (cache-key-consistency fix), so call.args is empty —
        # read call.kwargs["symbol"] instead of call.args[0].
        run_calls = [
            call.kwargs["symbol"] for call in mock_yahoo_instance._run.call_args_list
            if call.kwargs.get("symbol") != "AAPL"
        ]
        assert len(run_calls) <= 8

        # The primary company-info fetch itself must be a keyword call too —
        # regression guard for the cache-key-consistency fix.
        primary_calls = [
            call for call in mock_yahoo_instance._run.call_args_list
            if call.kwargs.get("symbol") == "AAPL"
        ]
        assert len(primary_calls) == 1
        assert primary_calls[0].args == ()

        # Stop words like SEC, ETF, NYSE, CEO, AND should not be in the run_calls
        blocklist = {"AND", "NYSE", "SEC", "ETF", "CEO"}
        for call_symbol in run_calls:
            assert call_symbol not in blocklist
            assert call_symbol != "AAPL"


class TestFreeIndustryAnalysisTool:
    """Tests for FreeIndustryAnalysisTool."""

    @patch('src.stock_analysis.tools.free_data_collection.FreeWebSearchTool')
    @patch('src.stock_analysis.tools.free_data_collection.FreeEconomicDataTool')
    @patch('src.stock_analysis.tools.free_data_collection.FreeNewsTool')
    def test_industry_analysis_parallel_fetching(self, mock_news_class, mock_economic_class, mock_search_class):
        """Test industry analysis runs sub-sources concurrently."""
        mock_search = Mock()
        mock_search._run.return_value = {"results": [{"title": "Search Result 1", "snippet": "Snippet"}]}
        mock_search_class.return_value = mock_search

        mock_economic = Mock()
        mock_economic._run.return_value = {"economic_data": {"gdp_growth": 2.5}}
        mock_economic_class.return_value = mock_economic

        mock_news = Mock()
        mock_news._run.return_value = {"news_data": [{"title": "News 1"}]}
        mock_news_class.return_value = mock_news

        tool = FreeIndustryAnalysisTool()
        result = tool._run(industry="Software", sector="Technology")

        assert result["industry"] == "Software"
        assert result["sector"] == "Technology"
        assert len(result["search_results"]) == 1
        assert result["economic_context"] == {"gdp_growth": 2.5}
        assert len(result["news_sentiment"]) == 1

        # Check all tools were called
        mock_search._run.assert_called_once()
        mock_economic._run.assert_called_once()
        mock_news._run.assert_called_once()


class TestFreeNewsToolFallbacks:
    """News collection must fall back Google News → Bing News → Yahoo feed."""

    @patch("src.stock_analysis.tools.cache._get_redis", return_value=None)
    @patch("src.stock_analysis.tools._http.SESSION.get")
    def test_bing_fallback_when_google_empty(self, mock_get, _redis):
        # FreeNewsTool._run now fetches each RSS feed via the shared HTTP
        # session (_http.get(url, timeout=15)) and passes resp.content to
        # feedparser.parse(...) instead of handing feedparser the raw URL
        # (fix: RSS fetching was bypassing the shared session's timeout/retry).
        import src.stock_analysis.tools.free_data_collection as fdc

        empty_feed = Mock(entries=[])
        bing_entry = {
            "title": "NVDA rallies", "summary": "chip demand", "link": "http://x",
        }
        bing_feed = Mock(entries=[bing_entry])

        # Distinct byte payloads per source so the feedparser.parse mock can
        # key off *content* (what the code now passes) rather than the URL.
        def _get(url, timeout=15, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock()
            if "news.google.com" in url:
                resp.content = b"google-empty-feed"
            elif "bing.com" in url:
                resp.content = b"bing-feed-content"
            else:
                resp.content = b"other-feed-content"
            return resp

        mock_get.side_effect = _get

        def _parse(content):
            if content == b"bing-feed-content":
                return bing_feed
            return empty_feed

        with patch.object(fdc, "feedparser") as mock_fp:
            mock_fp.parse.side_effect = _parse
            result = fdc.FreeNewsTool()._run("NVDA", limit=5)

        assert result["total_count"] == 1
        assert result["news_data"][0]["source"] == "Bing News"
        assert result["news_data"][0]["title"] == "NVDA rallies"

        # Google News and Bing were both fetched through the shared session,
        # each with the RSS URL and an explicit timeout — never a bare
        # feedparser.parse(url) call.
        fetched_urls = [c.args[0] if c.args else c.kwargs.get("url") for c in mock_get.call_args_list]
        assert any("news.google.com" in u for u in fetched_urls)
        assert any("bing.com" in u for u in fetched_urls)
        for c in mock_get.call_args_list:
            assert c.kwargs.get("timeout") == 15
        # feedparser.parse must have been called with bytes content, never a URL string.
        for parse_call in mock_fp.parse.call_args_list:
            arg = parse_call.args[0]
            assert isinstance(arg, bytes)


class TestCachingDecorators:
    """Verify caching decorators are applied and behave correctly."""

    def test_caching_decorator_presence(self):
        """Verify the decorators wrap the _run methods."""
        # If wrapped, they will have __wrapped__ attribute
        assert hasattr(FreeEconomicDataTool._run, "__wrapped__")
        assert hasattr(FreeCompetitorAnalysisTool._run, "__wrapped__")
        assert hasattr(FreeIndustryAnalysisTool._run, "__wrapped__")
        assert hasattr(FreeSECFilingTool._run, "__wrapped__")

    @patch('src.stock_analysis.tools.cache._get_redis')
    def test_cache_hits_and_misses(self, mock_get_redis):
        """Test cache interaction with a mock Redis client."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock Redis cache miss (get returns None)
        mock_redis.get.return_value = None

        # Create a mock tool to test the decorator wrapper logic
        # We can use FreeSECFilingTool with a mock requests/content logic
        tool = FreeSECFilingTool()

        with patch('src.stock_analysis.tools._http.SESSION.get') as mock_requests_get:
            mock_resp = Mock()
            mock_resp.content = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>10-K</title><link href="http://link"/></entry></feed>'
            mock_resp.raise_for_status = Mock()
            mock_resp.text = "mock filing content"
            mock_requests_get.return_value = mock_resp

            # First run: cache miss, should call requests.get and setex the cache
            res = tool._run("AAPL", limit=1)
            assert "filings" in res
            assert mock_redis.get.called
            assert mock_redis.setex.called

            # Now mock Redis cache hit
            cached_data = {"filings": [{"title": "Cached 10-K"}], "content": "cached content"}
            mock_redis.get.return_value = json.dumps(cached_data)

            # Second run: cache hit, should return cached data directly without requests.get
            mock_requests_get.reset_mock()
            res_cached = tool._run("AAPL", limit=1)
            assert res_cached["filings"][0]["title"] == "Cached 10-K"
            mock_requests_get.assert_not_called()


class TestPeriodNormalization:
    """LLM-invented period strings must never reach yfinance."""

    def test_aliases(self):
        from src.stock_analysis.tools.free_data_collection import _normalize_period
        assert _normalize_period("1-year") == "1y"
        assert _normalize_period("1 Year") == "1y"
        assert _normalize_period("12 months") == "1y"
        assert _normalize_period("6-month") == "6mo"
        assert _normalize_period("2 Years") == "2y"
        assert _normalize_period("1y") == "1y"  # already valid
        assert _normalize_period("ytd") == "ytd"

    def test_garbage_falls_back_to_default(self):
        from src.stock_analysis.tools.free_data_collection import _normalize_period
        assert _normalize_period("forever") == "1y"
        assert _normalize_period(None) == "1y"
        assert _normalize_period("", default="2y") == "2y"


class TestMemoryCacheFallback:
    """Without Redis, identical tool calls must return identical cached results."""

    @patch("src.stock_analysis.tools.cache._get_redis", return_value=None)
    def test_second_call_served_from_memory(self, _redis):
        from src.stock_analysis.tools.cache import cached_tool

        calls = {"n": 0}

        class _Tool:
            name = "memo-test"

            @cached_tool(ttl=60)
            def _run(self, symbol):
                calls["n"] += 1
                return {"symbol": symbol, "call": calls["n"]}

        t = _Tool()
        first = t._run("NVDA")
        second = t._run("NVDA")
        assert calls["n"] == 1            # underlying function ran once
        assert first == second            # identical → CrewAI loop guard can fire
        t._run("AAPL")
        assert calls["n"] == 2            # different args = different cache key

    @patch("src.stock_analysis.tools.cache._get_redis", return_value=None)
    def test_errors_not_cached_in_memory(self, _redis):
        from src.stock_analysis.tools.cache import cached_tool

        calls = {"n": 0}

        class _Tool:
            name = "memo-err"

            @cached_tool(ttl=60)
            def _run(self, symbol):
                calls["n"] += 1
                return {"error": "boom"}

        t = _Tool()
        t._run("X")
        t._run("X")
        assert calls["n"] == 2            # error responses are retried, never cached
