"""Tests for the tools/providers/ abstraction: base helpers, the keyless
yfinance provider, the FMP/Polygon premium clients (mocked HTTP, matching the
project convention for tools._http), and the router's fallback-chain logic."""

from unittest.mock import Mock, patch

import pytest

from src.stock_analysis.tools.providers import base


class TestProviderBaseDefaults:
    def test_unimplemented_capabilities_return_empty_dict(self):
        p = base.ProviderBase()
        assert p.get_quote("AAPL") == {}
        assert p.get_daily_bars("AAPL", "2026-01-01", "2026-01-31") == {}
        assert p.get_statements("AAPL") == {}
        assert p.get_estimates("AAPL") == {}
        assert p.get_transcript("AAPL") == {}
        assert p.get_insider_trades("AAPL") == {}
        assert p.get_calendar("AAPL") == {}
        assert p.get_etf_holdings("AAPL") == {}


class TestIsCapable:
    def test_none_is_not_capable(self):
        assert base.is_capable(None) is False

    def test_empty_dict_is_not_capable(self):
        assert base.is_capable({}) is False

    def test_error_dict_is_not_capable(self):
        assert base.is_capable({"error": "boom"}) is False

    def test_populated_dict_is_capable(self):
        assert base.is_capable({"price": 100.0}) is True


class TestYFinanceProvider:
    def _fake_ticker(self, monkeypatch, *, fast_info=None):
        from src.stock_analysis.tools.providers import yfinance_provider as mod

        class _FastInfo:
            def __init__(self, d):
                self._d = d

            def __getattr__(self, name):
                return self._d.get(name)

        class _T:
            def __init__(self, symbol):
                self.symbol = symbol
                self.fast_info = _FastInfo(fast_info or {})

        monkeypatch.setattr(mod, "YFinanceProvider", mod.YFinanceProvider)  # no-op, keeps import used
        return _T

    def test_get_quote_computes_change_pct(self, monkeypatch):
        from src.stock_analysis.tools.providers.yfinance_provider import YFinanceProvider

        provider = YFinanceProvider()
        fake = self._fake_ticker(monkeypatch, fast_info={
            "last_price": 110.0, "previous_close": 100.0, "last_volume": 5000,
        })
        monkeypatch.setattr(provider, "_ticker", lambda symbol: fake(symbol))

        result = provider.get_quote("AAPL")
        assert result["price"] == 110.0
        assert result["change_pct"] == pytest.approx(10.0)
        assert result["source"] == "yfinance"

    def test_get_quote_handles_exception(self, monkeypatch):
        from src.stock_analysis.tools.providers.yfinance_provider import YFinanceProvider

        provider = YFinanceProvider()
        monkeypatch.setattr(provider, "_ticker", lambda symbol: (_ for _ in ()).throw(RuntimeError("boom")))
        result = provider.get_quote("AAPL")
        assert "error" in result

    def test_get_statements_wraps_yf_summaries_and_tags_source(self, monkeypatch):
        from src.stock_analysis.tools import yf_summaries
        from src.stock_analysis.tools.providers.yfinance_provider import YFinanceProvider

        monkeypatch.setattr(
            yf_summaries, "summarize_financial_statements",
            lambda ticker: {"income_statement": {"2025": {"revenue_m": 100}}},
        )
        provider = YFinanceProvider()
        monkeypatch.setattr(provider, "_ticker", lambda symbol: object())
        result = provider.get_statements("AAPL")
        assert result["source"] == "yfinance"
        assert "income_statement" in result

    def test_get_transcript_is_a_capability_gap_not_an_error(self):
        from src.stock_analysis.tools.providers.yfinance_provider import YFinanceProvider

        assert YFinanceProvider().get_transcript("AAPL") == {}

    def test_get_daily_bars_empty_history_returns_empty_dict(self, monkeypatch):
        import pandas as pd

        from src.stock_analysis.tools.providers.yfinance_provider import YFinanceProvider

        class _T:
            def history(self, **kwargs):
                return pd.DataFrame()

        provider = YFinanceProvider()
        monkeypatch.setattr(provider, "_ticker", lambda symbol: _T())
        assert provider.get_daily_bars("AAPL", "2026-01-01", "2026-01-31") == {}

    def test_get_daily_bars_converts_rows(self, monkeypatch):
        import pandas as pd

        from src.stock_analysis.tools.providers.yfinance_provider import YFinanceProvider

        idx = pd.to_datetime(["2026-01-02", "2026-01-03"])
        hist = pd.DataFrame({
            "Open": [10.0, 11.0], "High": [12.0, 13.0], "Low": [9.0, 10.0],
            "Close": [11.0, 12.0], "Volume": [1000, 2000],
        }, index=idx)

        class _T:
            def history(self, **kwargs):
                return hist

        provider = YFinanceProvider()
        monkeypatch.setattr(provider, "_ticker", lambda symbol: _T())
        result = provider.get_daily_bars("AAPL", "2026-01-01", "2026-01-31")
        assert len(result["bars"]) == 2
        assert result["bars"][0]["close"] == 11.0


def _mock_response(payload):
    resp = Mock()
    resp.json.return_value = payload
    resp.raise_for_status = Mock()
    return resp


class TestFMPProvider:
    def test_get_quote_parses_first_result(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response([{
                "price": 150.0, "previousClose": 145.0, "changesPercentage": 3.4,
                "volume": 1_000_000, "marketCap": 2.5e12, "pe": 28.5,
            }])
            result = FMPProvider("test-key").get_quote("AAPL")
        assert result["price"] == 150.0
        assert result["source"] == "fmp"

    def test_get_quote_empty_response_returns_empty_dict(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response([])
            result = FMPProvider("test-key").get_quote("ZZZZ")
        assert result == {}

    def test_get_quote_http_error_returns_error_dict(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get", side_effect=ConnectionError("down")):
            result = FMPProvider("test-key").get_quote("AAPL")
        assert "error" in result

    def test_get_statements_shapes_three_statements(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        income = [{"calendarYear": "2025", "revenue": 1000, "netIncome": 100, "eps": 5.0}]
        balance = [{"calendarYear": "2025", "totalAssets": 5000}]
        cashflow = [{"calendarYear": "2025", "freeCashFlow": 200}]
        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.side_effect = [
                _mock_response(income), _mock_response(balance), _mock_response(cashflow),
            ]
            result = FMPProvider("test-key").get_statements("AAPL", years=10)
        assert result["years_available"] == 1
        assert result["income_statement"][0]["revenue"] == 1000
        assert result["balance_sheet"][0]["total_assets"] == 5000
        assert result["cash_flow"][0]["free_cash_flow"] == 200

    def test_get_transcript_two_step_fetch(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.side_effect = [
                _mock_response([{"year": 2026, "quarter": 2}]),
                _mock_response([{"content": "x" * 10000, "date": "2026-07-01"}]),
            ]
            result = FMPProvider("test-key").get_transcript("AAPL")
        assert result["year"] == 2026
        assert result["quarter"] == 2
        assert len(result["content_excerpt"]) == 6000

    def test_get_transcript_no_history_is_empty(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response([])
            result = FMPProvider("test-key").get_transcript("AAPL")
        assert result == {}

    def test_get_calendar_finds_next_future_earnings(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response([
                {"date": "2099-01-01", "epsEstimated": 1.5},
                {"date": "2020-01-01", "epsEstimated": 1.0},
            ])
            result = FMPProvider("test-key").get_calendar("AAPL")
        assert result["next_earnings"]["date"] == "2099-01-01"

    def test_get_insider_trades_shapes_rows(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response([
                {"reportingName": "Jane Doe", "transactionType": "S-Sale", "securitiesTransacted": 1000},
            ])
            result = FMPProvider("test-key").get_insider_trades("AAPL")
        assert result["insider_trades"][0]["reporting_name"] == "Jane Doe"

    def test_get_etf_holdings_combines_two_calls(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.side_effect = [
                _mock_response([{"asset": "AAPL", "weightPercentage": 7.1}]),
                _mock_response([{"sector": "Technology", "weightPercentage": 30.0}]),
            ]
            result = FMPProvider("test-key").get_etf_holdings("QQQ")
        assert result["top_holdings"][0]["name"] == "AAPL"
        assert result["sector_weightings_pct"]["Technology"] == 30.0

    def test_screener_returns_empty_without_key(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.fmp import screener

        monkeypatch.setattr(settings, "fmp_api_key", None)
        assert screener(sector="Technology") == []

    def test_screener_queries_with_criteria(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.fmp import screener

        monkeypatch.setattr(settings, "fmp_api_key", "test-key")
        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response([{"symbol": "AAPL"}])
            result = screener(sector="Technology", marketCapMoreThan=1e9)
        assert result == [{"symbol": "AAPL"}]
        _args, kwargs = mock_get.call_args
        assert kwargs["params"]["sector"] == "Technology"


class TestPolygonProvider:
    def test_get_quote_from_snapshot(self):
        from src.stock_analysis.tools.providers.polygon import PolygonProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response({
                "ticker": {
                    "day": {"c": 155.0, "v": 900000}, "prevDay": {"c": 150.0},
                    "todaysChangePerc": 3.33,
                }
            })
            result = PolygonProvider("test-key").get_quote("AAPL")
        assert result["price"] == 155.0
        assert result["source"] == "polygon"

    def test_get_quote_missing_price_is_empty(self):
        from src.stock_analysis.tools.providers.polygon import PolygonProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response({"ticker": {}})
            result = PolygonProvider("test-key").get_quote("ZZZZ")
        assert result == {}

    def test_get_daily_bars_converts_epoch_ms(self):
        from src.stock_analysis.tools.providers.polygon import PolygonProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response({
                "results": [{"t": 1767225600000, "o": 10, "h": 12, "l": 9, "c": 11, "v": 1000}]
            })
            result = PolygonProvider("test-key").get_daily_bars("AAPL", "2026-01-01", "2026-01-31")
        assert result["bars"][0]["close"] == 11
        assert result["bars"][0]["date"]  # parsed to a date string

    def test_get_batch_quotes_multiple_symbols(self):
        from src.stock_analysis.tools.providers.polygon import PolygonProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response({
                "tickers": [
                    {"ticker": "AAPL", "day": {"c": 150.0}, "prevDay": {"c": 148.0}},
                    {"ticker": "MSFT", "day": {"c": 300.0}, "prevDay": {"c": 298.0}},
                ]
            })
            result = PolygonProvider("test-key").get_batch_quotes(["AAPL", "MSFT"])
        assert result["AAPL"]["price"] == 150.0
        assert result["MSFT"]["price"] == 300.0

    def test_get_batch_quotes_empty_symbols_short_circuits(self):
        from src.stock_analysis.tools.providers.polygon import PolygonProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            result = PolygonProvider("test-key").get_batch_quotes([])
        assert result == {}
        mock_get.assert_not_called()


class TestProviderRouter:
    @pytest.fixture(autouse=True)
    def _clear_keys(self, monkeypatch):
        from src.stock_analysis.config.settings import settings

        monkeypatch.setattr(settings, "fmp_api_key", None)
        monkeypatch.setattr(settings, "polygon_api_key", None)

    def test_status_reflects_configured_keys(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.router import ProviderRouter

        monkeypatch.setattr(settings, "fmp_api_key", "key")
        router = ProviderRouter()
        status = router.status()
        assert status["fmp"]["configured"] is True
        assert status["polygon"]["configured"] is False
        assert status["yfinance"]["configured"] is True

    def test_keyless_quote_falls_through_to_yfinance(self, monkeypatch):
        from src.stock_analysis.tools.providers.router import ProviderRouter

        router = ProviderRouter()
        monkeypatch.setattr(router._yfinance, "get_quote", lambda symbol: {"price": 1.0, "source": "yfinance"})
        result = router.get_quote("AAPL")
        assert result["source"] == "yfinance"

    def test_polygon_preferred_over_yfinance_when_configured(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.router import ProviderRouter

        monkeypatch.setattr(settings, "polygon_api_key", "key")
        router = ProviderRouter()
        with patch("src.stock_analysis.tools.providers.polygon.PolygonProvider.get_quote",
                   return_value={"price": 2.0, "source": "polygon"}):
            result = router.get_quote("AAPL")
        assert result["source"] == "polygon"

    def test_falls_back_to_yfinance_when_polygon_fails(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.router import ProviderRouter

        monkeypatch.setattr(settings, "polygon_api_key", "key")
        router = ProviderRouter()
        monkeypatch.setattr(router._yfinance, "get_quote", lambda symbol: {"price": 1.0, "source": "yfinance"})
        with patch("src.stock_analysis.tools.providers.polygon.PolygonProvider.get_quote",
                   return_value={"error": "rate limited"}):
            result = router.get_quote("AAPL")
        assert result["source"] == "yfinance"

    def test_fmp_preferred_for_fundamentals_when_configured(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.router import ProviderRouter

        monkeypatch.setattr(settings, "fmp_api_key", "key")
        router = ProviderRouter()
        with patch("src.stock_analysis.tools.providers.fmp.FMPProvider.get_statements",
                   return_value={"years_available": 10, "source": "fmp"}):
            result = router.get_statements("AAPL")
        assert result["source"] == "fmp"

    def test_get_batch_quotes_empty_without_polygon_key(self):
        from src.stock_analysis.tools.providers.router import ProviderRouter

        router = ProviderRouter()
        assert router.get_batch_quotes(["AAPL"]) == {}

    def test_transcript_yfinance_gap_falls_through_cleanly(self, monkeypatch):
        """yfinance has no transcript capability at all; with no FMP key, the
        router must return {} rather than raise."""
        from src.stock_analysis.tools.providers.router import ProviderRouter

        router = ProviderRouter()
        assert router.get_transcript("AAPL") == {}
