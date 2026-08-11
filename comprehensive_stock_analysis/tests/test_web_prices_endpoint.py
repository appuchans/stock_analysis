"""Tests for GET /api/reports/{symbol}/prices — live price series for the
report Overview chart (period selector + comparison symbols)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.stock_analysis.web.app import app
from src.stock_analysis.web.price_series import ROUTER

client = TestClient(app)


def _bars(symbol):
    return {
        "symbol": symbol,
        "bars": [
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 101.0},
        ],
    }


class TestReportPricesEndpoint:
    def test_valid_symbol_default_period(self):
        with patch.object(ROUTER, "get_daily_bars", return_value=_bars("AAPL")):
            r = client.get("/api/reports/AAPL/prices")
        assert r.status_code == 200
        body = r.json()
        assert body["period"] == "1y"
        assert [s["symbol"] for s in body["series"]] == ["AAPL"]

    def test_with_compare_symbols(self):
        with patch.object(
            ROUTER, "get_daily_bars", side_effect=lambda s, a, b: _bars(s)
        ):
            r = client.get("/api/reports/AAPL/prices?compare=MSFT,GOOGL")
        assert r.status_code == 200
        symbols = [s["symbol"] for s in r.json()["series"]]
        assert symbols == ["AAPL", "MSFT", "GOOGL"]

    def test_invalid_primary_symbol_400(self):
        r = client.get("/api/reports/AAPL$/prices")
        assert r.status_code == 400

    def test_invalid_compare_symbol_dropped_not_errored(self):
        with patch.object(ROUTER, "get_daily_bars", return_value=_bars("AAPL")):
            r = client.get("/api/reports/AAPL/prices?compare=../evil")
        assert r.status_code == 200
        body = r.json()
        assert [s["symbol"] for s in body["series"]] == ["AAPL"]
        assert "../evil" in body["omitted"]

    def test_period_param_forwarded(self):
        with patch.object(ROUTER, "get_daily_bars", return_value=_bars("AAPL")):
            r = client.get("/api/reports/AAPL/prices?period=3mo")
        assert r.status_code == 200
        assert r.json()["period"] == "3mo"
