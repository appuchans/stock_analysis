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

        monkeypatch.setattr(
            mod, "YFinanceProvider", mod.YFinanceProvider
        )  # no-op, keeps import used
        return _T

    def test_get_quote_computes_change_pct(self, monkeypatch):
        from src.stock_analysis.tools.providers.yfinance_provider import (
            YFinanceProvider,
        )

        provider = YFinanceProvider()
        fake = self._fake_ticker(
            monkeypatch,
            fast_info={
                "last_price": 110.0,
                "previous_close": 100.0,
                "last_volume": 5000,
            },
        )
        monkeypatch.setattr(provider, "_ticker", lambda symbol: fake(symbol))

        result = provider.get_quote("AAPL")
        assert result["price"] == 110.0
        assert result["change_pct"] == pytest.approx(10.0)
        assert result["source"] == "yfinance"

    def test_get_quote_handles_exception(self, monkeypatch):
        from src.stock_analysis.tools.providers.yfinance_provider import (
            YFinanceProvider,
        )

        provider = YFinanceProvider()
        monkeypatch.setattr(
            provider,
            "_ticker",
            lambda symbol: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = provider.get_quote("AAPL")
        assert "error" in result

    def test_get_statements_wraps_yf_summaries_and_tags_source(self, monkeypatch):
        from src.stock_analysis.tools import yf_summaries
        from src.stock_analysis.tools.providers.yfinance_provider import (
            YFinanceProvider,
        )

        monkeypatch.setattr(
            yf_summaries,
            "summarize_financial_statements",
            lambda ticker: {"income_statement": {"2025": {"revenue_m": 100}}},
        )
        provider = YFinanceProvider()
        monkeypatch.setattr(provider, "_ticker", lambda symbol: object())
        result = provider.get_statements("AAPL")
        assert result["source"] == "yfinance"
        assert "income_statement" in result

    def test_get_transcript_is_a_capability_gap_not_an_error(self):
        from src.stock_analysis.tools.providers.yfinance_provider import (
            YFinanceProvider,
        )

        assert YFinanceProvider().get_transcript("AAPL") == {}

    def test_get_daily_bars_empty_history_returns_empty_dict(self, monkeypatch):
        import pandas as pd

        from src.stock_analysis.tools.providers.yfinance_provider import (
            YFinanceProvider,
        )

        class _T:
            def history(self, **kwargs):
                return pd.DataFrame()

        provider = YFinanceProvider()
        monkeypatch.setattr(provider, "_ticker", lambda symbol: _T())
        assert provider.get_daily_bars("AAPL", "2026-01-01", "2026-01-31") == {}

    def test_get_daily_bars_converts_rows(self, monkeypatch):
        import pandas as pd

        from src.stock_analysis.tools.providers.yfinance_provider import (
            YFinanceProvider,
        )

        idx = pd.to_datetime(["2026-01-02", "2026-01-03"])
        hist = pd.DataFrame(
            {
                "Open": [10.0, 11.0],
                "High": [12.0, 13.0],
                "Low": [9.0, 10.0],
                "Close": [11.0, 12.0],
                "Volume": [1000, 2000],
            },
            index=idx,
        )

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
            mock_get.return_value = _mock_response(
                [
                    {
                        "price": 150.0,
                        "previousClose": 145.0,
                        "changesPercentage": 3.4,
                        "volume": 1_000_000,
                        "marketCap": 2.5e12,
                        "pe": 28.5,
                    }
                ]
            )
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

        with patch(
            "src.stock_analysis.tools._http.SESSION.get",
            side_effect=ConnectionError("down"),
        ):
            result = FMPProvider("test-key").get_quote("AAPL")
        assert "error" in result

    def test_get_statements_shapes_three_statements(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        income = [
            {"calendarYear": "2025", "revenue": 1000, "netIncome": 100, "eps": 5.0}
        ]
        balance = [{"calendarYear": "2025", "totalAssets": 5000}]
        cashflow = [{"calendarYear": "2025", "freeCashFlow": 200}]
        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.side_effect = [
                _mock_response(income),
                _mock_response(balance),
                _mock_response(cashflow),
            ]
            result = FMPProvider("test-key").get_statements("AAPL", years=10)
        assert result["years_available"] == 1
        assert result["income_statement"][0]["revenue"] == 1000
        assert result["balance_sheet"][0]["total_assets"] == 5000
        assert result["cash_flow"][0]["free_cash_flow"] == 200

    def test_get_transcript_single_call_on_stable(self):
        """/stable serves the latest transcript in one call.

        The retired v3 API needed two (list available periods, then fetch the
        chosen one); the excerpt cap still applies since a full transcript runs
        tens of thousands of characters.
        """
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response(
                [
                    {
                        "fiscalYear": 2026,
                        "period": "Q2",
                        "date": "2026-07-01",
                        "content": "x" * 10000,
                    }
                ]
            )
            result = FMPProvider("test-key").get_transcript("AAPL")
        assert result["year"] == 2026
        assert result["quarter"] == "Q2"
        assert len(result["content_excerpt"]) == 6000

    def test_get_transcript_without_content_is_empty(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response([{"fiscalYear": 2026}])
            assert FMPProvider("test-key").get_transcript("AAPL") == {}

    def test_get_transcript_no_history_is_empty(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response([])
            result = FMPProvider("test-key").get_transcript("AAPL")
        assert result == {}

    def test_get_calendar_finds_next_future_earnings(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response(
                [
                    {"date": "2099-01-01", "epsEstimated": 1.5},
                    {"date": "2020-01-01", "epsEstimated": 1.0},
                ]
            )
            result = FMPProvider("test-key").get_calendar("AAPL")
        assert result["next_earnings"]["date"] == "2099-01-01"

    def test_get_insider_trades_shapes_rows(self):
        from src.stock_analysis.tools.providers.fmp import FMPProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response(
                [
                    {
                        "reportingName": "Jane Doe",
                        "transactionType": "S-Sale",
                        "securitiesTransacted": 1000,
                    },
                ]
            )
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
            mock_get.return_value = _mock_response(
                {
                    "ticker": {
                        "day": {"c": 155.0, "v": 900000},
                        "prevDay": {"c": 150.0},
                        "todaysChangePerc": 3.33,
                    }
                }
            )
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
            mock_get.return_value = _mock_response(
                {
                    "results": [
                        {
                            "t": 1767225600000,
                            "o": 10,
                            "h": 12,
                            "l": 9,
                            "c": 11,
                            "v": 1000,
                        }
                    ]
                }
            )
            result = PolygonProvider("test-key").get_daily_bars(
                "AAPL", "2026-01-01", "2026-01-31"
            )
        assert result["bars"][0]["close"] == 11
        assert result["bars"][0]["date"]  # parsed to a date string

    def test_get_batch_quotes_multiple_symbols(self):
        from src.stock_analysis.tools.providers.polygon import PolygonProvider

        with patch("src.stock_analysis.tools._http.SESSION.get") as mock_get:
            mock_get.return_value = _mock_response(
                {
                    "tickers": [
                        {
                            "ticker": "AAPL",
                            "day": {"c": 150.0},
                            "prevDay": {"c": 148.0},
                        },
                        {
                            "ticker": "MSFT",
                            "day": {"c": 300.0},
                            "prevDay": {"c": 298.0},
                        },
                    ]
                }
            )
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
        monkeypatch.setattr(
            router._yfinance,
            "get_quote",
            lambda symbol: {"price": 1.0, "source": "yfinance"},
        )
        result = router.get_quote("AAPL")
        assert result["source"] == "yfinance"

    def test_polygon_preferred_over_yfinance_when_configured(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.router import ProviderRouter

        monkeypatch.setattr(settings, "polygon_api_key", "key")
        router = ProviderRouter()
        with patch(
            "src.stock_analysis.tools.providers.polygon.PolygonProvider.get_quote",
            return_value={"price": 2.0, "source": "polygon"},
        ):
            result = router.get_quote("AAPL")
        assert result["source"] == "polygon"

    def test_falls_back_to_yfinance_when_polygon_fails(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.router import ProviderRouter

        monkeypatch.setattr(settings, "polygon_api_key", "key")
        router = ProviderRouter()
        monkeypatch.setattr(
            router._yfinance,
            "get_quote",
            lambda symbol: {"price": 1.0, "source": "yfinance"},
        )
        with patch(
            "src.stock_analysis.tools.providers.polygon.PolygonProvider.get_quote",
            return_value={"error": "rate limited"},
        ):
            result = router.get_quote("AAPL")
        assert result["source"] == "yfinance"

    def test_fmp_preferred_for_fundamentals_when_configured(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.tools.providers.router import ProviderRouter

        monkeypatch.setattr(settings, "fmp_api_key", "key")
        router = ProviderRouter()
        with patch(
            "src.stock_analysis.tools.providers.fmp.FMPProvider.get_statements",
            return_value={"years_available": 10, "source": "fmp"},
        ):
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


class TestFMPStableApi:
    """FMP's /api/v3 and /api/v4 were retired 2025-08-31.

    Any key issued after that date gets 403 "Legacy Endpoint" from the old
    paths, which made every premium capability silently degrade to yfinance.
    These guard that we call /stable and that tier limits read as capability
    gaps rather than errors.
    """

    def test_base_url_is_the_stable_api(self):
        from src.stock_analysis.tools.providers import fmp

        assert fmp._BASE_URL == "https://financialmodelingprep.com/stable"
        assert "/api/v3" not in fmp._BASE_URL
        assert "/api/v4" not in fmp._BASE_URL

    def test_symbol_is_passed_as_a_query_param_not_a_path_segment(self, monkeypatch):
        """/stable moved the symbol out of the URL path."""
        from src.stock_analysis.tools.providers import fmp

        seen = {}

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return [{"price": 1.0}]

        def _fake_get(url, params=None, timeout=None):
            seen["url"] = url
            seen["params"] = params
            return _Resp()

        monkeypatch.setattr(fmp._http, "get", _fake_get)
        fmp.FMPProvider("k").get_quote("AAPL")

        assert seen["url"].endswith("/stable/quote")
        assert seen["params"]["symbol"] == "AAPL"

    @pytest.mark.parametrize("status", [402, 403])
    def test_tier_limited_endpoint_is_a_capability_gap_not_an_error(
        self, monkeypatch, status
    ):
        """402/403 means 'not in your plan' — the router must fall through to
        yfinance, which only happens for {} (see providers/base.is_capable)."""
        from src.stock_analysis.tools.providers import fmp
        from src.stock_analysis.tools.providers.base import is_capable

        class _Resp:
            def __init__(self):
                self.status_code = status

            def raise_for_status(self):
                raise AssertionError("must not raise before the tier check")

            def json(self):
                return {}

        monkeypatch.setattr(fmp._http, "get", lambda *a, **k: _Resp())
        p = fmp.FMPProvider("k")
        for result in (
            p.get_insider_trades("AAPL"),
            p.get_etf_holdings("SPY"),
            p.get_transcript("AAPL"),
            p.get_revenue_segments("AAPL"),
        ):
            assert result == {}
            assert is_capable(result) is False

    def test_revenue_segments_shape(self, monkeypatch):
        from src.stock_analysis.tools.providers import fmp

        payload = [
            {
                "symbol": "AMZN",
                "fiscalYear": 2025,
                "date": "2025-12-31",
                "reportedCurrency": "USD",
                "data": {"AWS": 25.0, "Ads": 75.0},
            }
        ]

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(fmp._http, "get", lambda *a, **k: _Resp())
        out = fmp.FMPProvider("k").get_revenue_segments("AMZN")

        latest = out["by_product"][0]
        assert latest["total"] == 100.0
        # Sorted biggest-first, with each share of the total computed.
        assert list(latest["segments"]) == ["Ads", "AWS"]
        assert latest["segments"]["Ads"]["pct_of_total"] == 75.0
        assert latest["segments"]["AWS"]["pct_of_total"] == 25.0

    def test_daily_bars_are_returned_oldest_first(self, monkeypatch):
        """/stable returns newest-first; charts need ascending dates."""
        from src.stock_analysis.tools.providers import fmp

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return [
                    {"date": "2026-07-03", "close": 3},
                    {"date": "2026-07-01", "close": 1},
                    {"date": "2026-07-02", "close": 2},
                ]

        monkeypatch.setattr(fmp._http, "get", lambda *a, **k: _Resp())
        bars = fmp.FMPProvider("k").get_daily_bars("AAPL", "2026-07-01", "2026-07-03")
        assert [b["close"] for b in bars["bars"]] == [1, 2, 3]

    def test_yfinance_reports_segments_as_a_capability_gap(self):
        from src.stock_analysis.tools.providers.yfinance_provider import (
            YFinanceProvider,
        )

        assert YFinanceProvider().get_revenue_segments("AAPL") == {}


class TestSecApiProvider:
    """sec-api.io: Form 4 detail and 10-K sections.

    Fills the insider gap FMP's free tier leaves (402), and replaces scraped
    filing HTML with parsed text.
    """

    def _provider(self):
        from src.stock_analysis.tools.providers.sec_api import SecApiProvider

        return SecApiProvider("test-key")

    def test_open_market_summary_excludes_compensation_mechanics(self, monkeypatch):
        """Grants/gifts/tax withholding are not conviction signals.

        Counting them as 'insider selling' is how a routine vesting schedule
        gets reported as executives dumping stock.
        """
        from src.stock_analysis.tools.providers import sec_api

        def _txn(code, disposed, shares, price):
            return {
                "securityTitle": "Common Stock",
                "transactionDate": "2026-08-06",
                "coding": {"code": code},
                "amounts": {
                    "shares": shares,
                    "pricePerShare": price,
                    "acquiredDisposedCode": "D" if disposed else "A",
                },
            }

        payload = {
            "transactions": [
                {
                    "reportingOwner": {
                        "name": "Jane Doe",
                        "relationship": {"isOfficer": True, "officerTitle": "CFO"},
                    },
                    "nonDerivativeTable": {
                        "transactions": [
                            _txn("S", True, 100, 10.0),   # open-market sale
                            _txn("P", False, 50, 10.0),   # open-market buy
                            _txn("G", True, 9999, 0),     # gift — must be excluded
                            _txn("A", False, 5000, 0),    # grant — must be excluded
                        ]
                    },
                }
            ]
        }

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(sec_api._http, "post", lambda *a, **k: _Resp())
        out = self._provider().get_insider_trades("AMZN")

        s = out["open_market_summary"]
        assert s["sell_count"] == 1 and s["buy_count"] == 1
        assert s["sell_value"] == 1000.0
        assert s["buy_value"] == 500.0
        assert s["net_value"] == -500.0
        # All four still listed, each labelled with what it actually was.
        assert len(out["insider_trades"]) == 4
        kinds = {t["transaction_type"] for t in out["insider_trades"]}
        assert {"open-market sale", "open-market buy", "gift", "grant/award"} == kinds

    def test_no_transactions_is_a_capability_gap(self, monkeypatch):
        from src.stock_analysis.tools.providers import sec_api

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"transactions": []}

        monkeypatch.setattr(sec_api._http, "post", lambda *a, **k: _Resp())
        assert self._provider().get_insider_trades("AMZN") == {}

    def test_filing_sections_are_unescaped_and_capped(self, monkeypatch):
        from src.stock_analysis.tools.providers import sec_api

        class _PostResp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "filings": [
                        {
                            "formType": "10-K",
                            "filedAt": "2026-02-05T00:00:00-05:00",
                            "accessionNo": "x",
                            "linkToFilingDetails": "https://example.com/f.htm",
                        }
                    ]
                }

        class _GetResp:
            status_code = 200
            text = "Item 1. Business ##TABLE_END Management&#8217;s view. " + "y" * 20000

        monkeypatch.setattr(sec_api._http, "post", lambda *a, **k: _PostResp())
        monkeypatch.setattr(sec_api._http, "get", lambda *a, **k: _GetResp())
        out = self._provider().get_filing_sections("AMZN")

        body = out["sections"]["business"]
        assert "##TABLE_END" not in body
        # &#8217; decodes to a curly apostrophe, not a straight one.
        assert "&#8217;" not in body and "Management’s view" in body
        assert len(body) <= sec_api._SECTION_CHAR_CAP

    def test_error_is_reported_as_error_not_a_gap(self, monkeypatch):
        """A real failure must not look like 'this provider has no such data',
        or the router would stop trying the rest of the chain silently."""
        from src.stock_analysis.tools.providers import sec_api

        def _boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr(sec_api._http, "post", _boom)
        assert "error" in self._provider().get_insider_trades("AMZN")

    def test_router_prefers_sec_api_for_insider_trades(self, monkeypatch):
        from src.stock_analysis.config import settings as settings_mod
        from src.stock_analysis.tools.providers import router as router_mod

        monkeypatch.setattr(settings_mod.settings, "sec_api_key", "k")
        chain = router_mod.ProviderRouter()._filings_chain()
        assert chain[0].name == "sec_api"

    def test_router_omits_sec_api_when_unconfigured(self, monkeypatch):
        from src.stock_analysis.config import settings as settings_mod
        from src.stock_analysis.tools.providers import router as router_mod

        monkeypatch.setattr(settings_mod.settings, "sec_api_key", None)
        chain = router_mod.ProviderRouter()._filings_chain()
        assert all(p.name != "sec_api" for p in chain)


class TestFinnhubProvider:
    def _p(self):
        from src.stock_analysis.tools.providers.finnhub import FinnhubProvider

        return FinnhubProvider("k")

    def _stub(self, monkeypatch, payload, status=200):
        from src.stock_analysis.tools.providers import finnhub

        class _R:
            status_code = status

            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(finnhub._http, "get", lambda *a, **k: _R())

    def test_recommendation_trend_computes_bullish_share(self, monkeypatch):
        self._stub(
            monkeypatch,
            [
                {
                    "period": "2026-08-01",
                    "strongBuy": 13,
                    "buy": 24,
                    "hold": 14,
                    "sell": 3,
                    "strongSell": 0,
                }
            ],
        )
        row = self._p().get_recommendation_trends("AAPL")["recommendation_trend"][0]
        assert row["total_analysts"] == 54
        assert row["bullish_pct"] == pytest.approx(68.5, abs=0.1)

    def test_earnings_surprises_count_beats_and_misses(self, monkeypatch):
        self._stub(
            monkeypatch,
            [
                {"period": "2026-06-30", "surprise": -0.02, "actual": 1.91},
                {"period": "2026-03-31", "surprise": 0.05, "actual": 1.60},
                {"period": "2025-12-31", "surprise": 0.10, "actual": 2.40},
            ],
        )
        out = self._p().get_earnings_surprises("AAPL")
        assert out["beats"] == 2 and out["misses"] == 1
        # Newest first.
        assert out["quarters"][0]["period"] == "2026-06-30"
        assert out["quarters"][0]["beat"] is False

    def test_rate_limit_is_a_capability_gap_not_an_error(self, monkeypatch):
        """429 must not surface as an error in a client-facing report."""
        self._stub(monkeypatch, {}, status=429)
        p = self._p()
        assert p.get_recommendation_trends("AAPL") == {}
        assert p.get_earnings_surprises("AAPL") == {}
        assert p.get_company_news("AAPL") == {}

    def test_unknown_symbol_zero_quote_is_a_gap(self, monkeypatch):
        self._stub(monkeypatch, {"c": 0, "pc": 0})
        assert self._p().get_quote("ZZZZ") == {}


class TestNewsSentimentProviders:
    def test_alpha_vantage_relevance_weighted_average(self, monkeypatch):
        """A passing mention in a macro piece must not sway the average as much
        as a story about the company itself."""
        from src.stock_analysis.tools.providers import news_sentiment as ns

        payload = {
            "feed": [
                {
                    "title": "About Apple",
                    "time_published": "20260814T093000",
                    "ticker_sentiment": [
                        {
                            "ticker": "AAPL",
                            "relevance_score": "1.0",
                            "ticker_sentiment_score": "0.5",
                            "ticker_sentiment_label": "Bullish",
                        }
                    ],
                },
                {
                    "title": "Macro piece",
                    "time_published": "20260814T093000",
                    "ticker_sentiment": [
                        {
                            "ticker": "AAPL",
                            "relevance_score": "0.0",
                            "ticker_sentiment_score": "-0.9",
                            "ticker_sentiment_label": "Bearish",
                        }
                    ],
                },
            ]
        }

        class _R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(ns._http, "get", lambda *a, **k: _R())
        out = ns.AlphaVantageNewsProvider("k").get_news_sentiment("AAPL")
        # Zero-relevance bearish article is weighted out entirely.
        assert out["sentiment"]["avg_sentiment_score"] == pytest.approx(0.5)
        assert out["sentiment"]["label"] == "bullish"

    def test_alpha_vantage_quota_note_is_a_gap_not_an_error(self, monkeypatch):
        """AV signals quota exhaustion with HTTP 200 + a Note key."""
        from src.stock_analysis.tools.providers import news_sentiment as ns

        class _R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"Note": "rate limit"}

        monkeypatch.setattr(ns._http, "get", lambda *a, **k: _R())
        assert ns.AlphaVantageNewsProvider("k").get_news_sentiment("AAPL") == {}

    def test_marketaux_normalises_onto_the_same_shape(self, monkeypatch):
        from src.stock_analysis.tools.providers import news_sentiment as ns

        payload = {
            "data": [
                {
                    "title": "Apple news",
                    "published_at": "2026-08-14T09:30:00.000000Z",
                    "entities": [
                        {
                            "symbol": "AAPL",
                            "sentiment_score": 0.4,
                            "match_score": 7.66,
                            "highlights": [{"highlight": "the sentence"}],
                        }
                    ],
                }
            ]
        }

        class _R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(ns._http, "get", lambda *a, **k: _R())
        out = ns.MarketauxNewsProvider("k").get_news_sentiment("AAPL")
        a = out["articles"][0]
        assert a["sentiment_score"] == 0.4
        assert a["sentiment_label"] == "bullish"
        assert a["highlight"] == "the sentence"
        # match_score is absolute; normalised to 0..1 so the weighted average
        # stays comparable with Alpha Vantage's relevance_score.
        assert 0.0 <= a["relevance"] <= 1.0
        assert out["sentiment"]["label"] == "bullish"

    def test_chain_prefers_alpha_vantage(self, monkeypatch):
        from src.stock_analysis.config import settings as sm
        from src.stock_analysis.tools.providers import router as rm

        monkeypatch.setattr(sm.settings, "alpha_vantage_api_key", "a")
        monkeypatch.setattr(sm.settings, "marketaux_api_key", "m")
        chain = rm.ProviderRouter()._news_sentiment_chain()
        assert [p.name for p in chain] == ["alpha_vantage", "marketaux"]

    def test_chain_empty_without_keys(self, monkeypatch):
        from src.stock_analysis.config import settings as sm
        from src.stock_analysis.tools.providers import router as rm

        monkeypatch.setattr(sm.settings, "alpha_vantage_api_key", None)
        monkeypatch.setattr(sm.settings, "marketaux_api_key", None)
        assert rm.ProviderRouter()._news_sentiment_chain() == []
