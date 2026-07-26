"""Tests for GET /api/portfolio/dashboard."""

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.stock_analysis.web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    from src.stock_analysis.web import db as db_mod

    monkeypatch.setattr(db_mod, "_db_path", lambda: tmp_path / "app.db")
    monkeypatch.setattr(db_mod, "_initialized", False)
    yield


class TestDashboardEmpty:
    def test_no_holdings_returns_empty_shape(self):
        resp = client.get("/api/portfolio/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["positions"] == []
        assert body["total_market_value"] == 0.0


class TestDashboardWithHoldings:
    def _seed(self):
        client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "buy", "qty": 10, "price": 100.0, "date": "2026-01-01",
        })

    def test_positions_enriched_with_live_quote(self, monkeypatch):
        from src.stock_analysis.tools.providers.router import ROUTER

        self._seed()
        monkeypatch.setattr(ROUTER, "get_batch_quotes", lambda syms: {})
        monkeypatch.setattr(ROUTER, "get_quote", lambda sym: {"price": 150.0, "change_pct": 2.5})

        with patch("yfinance.download", side_effect=RuntimeError("no network in test")):
            resp = client.get("/api/portfolio/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["positions"]) == 1
        pos = body["positions"][0]
        assert pos["symbol"] == "AAPL"
        assert pos["current_price"] == 150.0
        assert pos["market_value"] == 1500.0
        assert pos["unrealized_pnl"] == 500.0
        assert pos["weight"] == 1.0
        assert body["total_market_value"] == 1500.0
        assert body["total_unrealized_pnl"] == 500.0

    def test_history_fetch_failure_still_returns_positions(self, monkeypatch):
        """Best-effort history/benchmark: a yfinance failure must not break
        the whole dashboard response."""
        from src.stock_analysis.tools.providers.router import ROUTER

        self._seed()
        monkeypatch.setattr(ROUTER, "get_batch_quotes", lambda syms: {})
        monkeypatch.setattr(ROUTER, "get_quote", lambda sym: {"price": 150.0})

        with patch("yfinance.download", side_effect=RuntimeError("network down")):
            resp = client.get("/api/portfolio/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["positions"]) == 1
        assert body["value_series"] == []
        assert body["benchmark_comparison"] is None

    def test_batch_quotes_preferred_over_per_symbol(self, monkeypatch):
        from src.stock_analysis.tools.providers.router import ROUTER

        self._seed()
        monkeypatch.setattr(ROUTER, "get_batch_quotes", lambda syms: {"AAPL": {"price": 200.0}})

        def _should_not_be_called(sym):
            raise AssertionError("get_quote must not be called when batch already has this symbol")

        monkeypatch.setattr(ROUTER, "get_quote", _should_not_be_called)
        with patch("yfinance.download", side_effect=RuntimeError("no network in test")):
            resp = client.get("/api/portfolio/dashboard")
        assert resp.json()["positions"][0]["current_price"] == 200.0

    def test_missing_quote_leaves_market_value_none(self, monkeypatch):
        from src.stock_analysis.tools.providers.router import ROUTER

        self._seed()
        monkeypatch.setattr(ROUTER, "get_batch_quotes", lambda syms: {})
        monkeypatch.setattr(ROUTER, "get_quote", lambda sym: {})

        with patch("yfinance.download", side_effect=RuntimeError("no network in test")):
            resp = client.get("/api/portfolio/dashboard")
        pos = resp.json()["positions"][0]
        assert pos["current_price"] is None
        assert pos["market_value"] is None
        assert pos["weight"] is None

    def test_value_series_and_benchmark_populated_when_history_available(self, monkeypatch):
        from src.stock_analysis.tools.providers.router import ROUTER

        self._seed()
        monkeypatch.setattr(ROUTER, "get_batch_quotes", lambda syms: {})
        monkeypatch.setattr(ROUTER, "get_quote", lambda sym: {"price": 150.0})

        dates = pd.date_range("2026-01-01", periods=10, freq="B")
        close = pd.DataFrame({
            "AAPL": [100.0 + i for i in range(10)],
            "SPY": [400.0 + i * 0.5 for i in range(10)],
        }, index=dates)
        fake_download = pd.concat({"Close": close}, axis=1)

        with patch("yfinance.download", return_value=fake_download):
            resp = client.get("/api/portfolio/dashboard")
        body = resp.json()
        assert len(body["value_series"]) > 0
        assert body["benchmark_comparison"] is not None
        assert "beta" in body["benchmark_comparison"]
