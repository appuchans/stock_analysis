"""Tests for the stock-comparison endpoints: GET /api/compare/metrics and
GET /api/compare/prices."""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.stock_analysis.config import settings as settings_mod
from src.stock_analysis.web.app import app
from src.stock_analysis.web.price_series import ROUTER

client = TestClient(app)


def _bars(symbol):
    return {"symbol": symbol, "bars": [{"date": "2026-01-01", "close": 100.0}]}


def _fake_ticker(info):
    t = MagicMock()
    t.info = info
    return t


_AAPL_INFO = {
    "shortName": "Apple Inc.",
    "marketCap": 3_000_000_000_000,
    "currentPrice": 200.0,
    "trailingPE": 30.0,
    "forwardPE": 28.0,
    "beta": 1.2,
    "fiftyTwoWeekLow": 150.0,
    "fiftyTwoWeekHigh": 220.0,
    "revenueGrowth": 0.05,
    "operatingMargins": 0.3,
}


class TestCompareMetricsEndpoint:
    def test_valid_symbols_returns_rows(self):
        with (
            patch(
                "src.stock_analysis.web.routes.compare.yf.Ticker",
                return_value=_fake_ticker(_AAPL_INFO),
            ),
            patch(
                "src.stock_analysis.web.routes.compare.summarize_analyst_data",
                return_value={"price_targets": {"mean": 210.0}},
            ),
        ):
            r = client.get("/api/compare/metrics?symbols=AAPL,MSFT")
        assert r.status_code == 200
        body = r.json()
        assert len(body["symbols"]) == 2
        row = body["symbols"][0]
        assert row["symbol"] == "AAPL"
        assert row["key_stats"]["market_cap_b"] == 3000.0
        assert row["analyst"]["price_targets"]["mean"] == 210.0
        assert row["has_report"] is False

    def test_untradeable_symbol_omitted(self):
        def fake_ticker(sym):
            return _fake_ticker(_AAPL_INFO if sym == "AAPL" else {})

        with (
            patch(
                "src.stock_analysis.web.routes.compare.yf.Ticker",
                side_effect=fake_ticker,
            ),
            patch(
                "src.stock_analysis.web.routes.compare.summarize_analyst_data",
                return_value={},
            ),
        ):
            r = client.get("/api/compare/metrics?symbols=AAPL,ZZZZNOTREAL")
        body = r.json()
        assert [s["symbol"] for s in body["symbols"]] == ["AAPL"]
        assert "ZZZZNOTREAL" in body["omitted"]

    def test_invalid_symbol_syntax_omitted(self):
        with (
            patch(
                "src.stock_analysis.web.routes.compare.yf.Ticker",
                return_value=_fake_ticker(_AAPL_INFO),
            ),
            patch(
                "src.stock_analysis.web.routes.compare.summarize_analyst_data",
                return_value={},
            ),
        ):
            r = client.get("/api/compare/metrics?symbols=AAPL,../evil")
        body = r.json()
        assert [s["symbol"] for s in body["symbols"]] == ["AAPL"]
        assert "../evil" in body["omitted"]

    def test_caps_at_max_symbols(self):
        symbols = ",".join(f"SYM{i}" for i in range(10))
        with (
            patch(
                "src.stock_analysis.web.routes.compare.yf.Ticker",
                return_value=_fake_ticker(_AAPL_INFO),
            ),
            patch(
                "src.stock_analysis.web.routes.compare.summarize_analyst_data",
                return_value={},
            ),
        ):
            r = client.get(f"/api/compare/metrics?symbols={symbols}")
        assert len(r.json()["symbols"]) == 4

    def test_has_report_true_when_chart_data_exists(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))
        (tmp_path / "AAPL").mkdir(parents=True)
        (tmp_path / "AAPL" / "AAPL_chart_data.json").write_text(
            json.dumps(
                {
                    "sentiment_snapshot": {"fear_greed_score": 55},
                    "valuation_scenarios": [{"scenario": "base"}],
                }
            ),
            encoding="utf-8",
        )
        with (
            patch(
                "src.stock_analysis.web.routes.compare.yf.Ticker",
                return_value=_fake_ticker(_AAPL_INFO),
            ),
            patch(
                "src.stock_analysis.web.routes.compare.summarize_analyst_data",
                return_value={},
            ),
        ):
            r = client.get("/api/compare/metrics?symbols=AAPL")
        row = r.json()["symbols"][0]
        assert row["has_report"] is True
        assert row["sentiment_snapshot"]["fear_greed_score"] == 55
        assert row["valuation_scenarios"] == [{"scenario": "base"}]

    def test_repeat_request_hits_cache(self):
        with (
            patch(
                "src.stock_analysis.web.routes.compare.yf.Ticker",
                return_value=_fake_ticker(_AAPL_INFO),
            ) as ticker_mock,
            patch(
                "src.stock_analysis.web.routes.compare.summarize_analyst_data",
                return_value={},
            ),
        ):
            client.get("/api/compare/metrics?symbols=AAPL")
            client.get("/api/compare/metrics?symbols=AAPL")
        assert ticker_mock.call_count == 1


class TestComparePricesEndpoint:
    def test_valid_symbols_returns_series(self):
        with patch.object(
            ROUTER, "get_daily_bars", side_effect=lambda s, a, b: _bars(s)
        ):
            r = client.get("/api/compare/prices?symbols=AAPL,MSFT")
        assert r.status_code == 200
        symbols = [s["symbol"] for s in r.json()["series"]]
        assert symbols == ["AAPL", "MSFT"]

    def test_period_param_forwarded(self):
        with patch.object(ROUTER, "get_daily_bars", return_value=_bars("AAPL")):
            r = client.get("/api/compare/prices?symbols=AAPL&period=5y")
        assert r.json()["period"] == "5y"
