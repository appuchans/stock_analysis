"""Tests for the shared live price-series helper (web/price_series.py) used by
the report Overview chart and the stock-comparison page."""

from unittest.mock import patch

from src.stock_analysis.web import price_series


def _bars(symbol, n=3):
    return {
        "symbol": symbol,
        "source": "yfinance",
        "bars": [
            {
                "date": f"2026-01-0{i+1}",
                "close": 100.0 + i,
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "volume": 1000,
            }
            for i in range(n)
        ],
    }


class TestFetchPriceSeries:
    def test_single_valid_symbol_returns_series(self):
        with patch.object(
            price_series.ROUTER, "get_daily_bars", return_value=_bars("AAPL")
        ):
            result = price_series.fetch_price_series(["AAPL"], "1y")
        assert result["period"] == "1y"
        assert len(result["series"]) == 1
        assert result["series"][0]["symbol"] == "AAPL"
        assert len(result["series"][0]["bars"]) == 3
        assert result["omitted"] == []

    def test_invalid_symbol_omitted_not_errored(self):
        with patch.object(
            price_series.ROUTER, "get_daily_bars", return_value=_bars("AAPL")
        ):
            result = price_series.fetch_price_series(["AAPL", "../evil"], "1y")
        assert len(result["series"]) == 1
        assert "../evil" in result["omitted"]

    def test_provider_failure_omits_symbol(self):
        def fake(sym, start, end):
            return {"error": "no data"} if sym == "BADCO" else _bars(sym)

        with patch.object(price_series.ROUTER, "get_daily_bars", side_effect=fake):
            result = price_series.fetch_price_series(["AAPL", "BADCO"], "1y")
        symbols = [s["symbol"] for s in result["series"]]
        assert symbols == ["AAPL"]
        assert "BADCO" in result["omitted"]

    def test_capability_gap_empty_dict_omits_symbol(self):
        def fake(sym, start, end):
            return {} if sym == "ETF1" else _bars(sym)

        with patch.object(price_series.ROUTER, "get_daily_bars", side_effect=fake):
            result = price_series.fetch_price_series(["AAPL", "ETF1"], "1y")
        assert "ETF1" in result["omitted"]

    def test_unknown_period_falls_back_to_default(self):
        with patch.object(
            price_series.ROUTER, "get_daily_bars", return_value=_bars("AAPL")
        ) as m:
            result = price_series.fetch_price_series(["AAPL"], "decade")
        assert result["period"] == price_series.DEFAULT_PERIOD
        m.assert_called_once()

    def test_caps_at_max_symbols(self):
        symbols = [f"SYM{i}" for i in range(10)]
        with patch.object(
            price_series.ROUTER, "get_daily_bars", side_effect=lambda s, a, b: _bars(s)
        ) as m:
            result = price_series.fetch_price_series(symbols, "1y")
        assert len(result["series"]) == price_series.MAX_SYMBOLS
        assert m.call_count == price_series.MAX_SYMBOLS

    def test_dedupes_symbols(self):
        with patch.object(
            price_series.ROUTER, "get_daily_bars", return_value=_bars("AAPL")
        ) as m:
            result = price_series.fetch_price_series(["AAPL", "aapl", "AAPL"], "1y")
        assert len(result["series"]) == 1
        m.assert_called_once()

    def test_repeat_request_hits_cache(self):
        with patch.object(
            price_series.ROUTER, "get_daily_bars", return_value=_bars("AAPL")
        ) as m:
            price_series.fetch_price_series(["AAPL"], "1y")
            price_series.fetch_price_series(["AAPL"], "1y")
        m.assert_called_once()

    def test_different_period_bypasses_cache(self):
        with patch.object(
            price_series.ROUTER, "get_daily_bars", return_value=_bars("AAPL")
        ) as m:
            price_series.fetch_price_series(["AAPL"], "1y")
            price_series.fetch_price_series(["AAPL"], "3mo")
        assert m.call_count == 2

    def test_empty_symbol_list_returns_empty_series(self):
        result = price_series.fetch_price_series([], "1y")
        assert result["series"] == []
