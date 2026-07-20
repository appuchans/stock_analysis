"""Tests for POST /api/portfolio/analyze and the /api/watchlist CRUD endpoints."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.stock_analysis.web.routes.portfolio import router as portfolio_router
from src.stock_analysis.web.routes.watchlist import router as watchlist_router

# Build a minimal test app that includes only the new routers.
# app.py does not wire them yet ("will be wired up separately").
_test_app = FastAPI()
_test_app.include_router(portfolio_router)
_test_app.include_router(watchlist_router)

client = TestClient(_test_app)

# ── Portfolio ──────────────────────────────────────────────────────────────────

_GOOD_PORTFOLIO_RESULT = {
    "symbols": ["AAPL", "MSFT"],
    "period": "1y",
    "correlation_matrix": {"AAPL": {"AAPL": 1.0, "MSFT": 0.85}, "MSFT": {"AAPL": 0.85, "MSFT": 1.0}},
    "individual_metrics": {
        "AAPL": {"annualised_return_pct": 12.5, "annualised_volatility_pct": 18.0,
                 "sharpe_ratio": 0.58, "max_drawdown_pct": -15.0, "var_95_daily_pct": -2.1},
        "MSFT": {"annualised_return_pct": 14.0, "annualised_volatility_pct": 17.5,
                 "sharpe_ratio": 0.69, "max_drawdown_pct": -12.0, "var_95_daily_pct": -1.9},
    },
    "equal_weight_allocation": {"AAPL": 0.5, "MSFT": 0.5},
    "min_variance_weights": {"AAPL": 0.48, "MSFT": 0.52},
    "portfolio_metrics": {
        "annualised_return_pct": 13.2, "annualised_volatility_pct": 16.9,
        "sharpe_ratio": 0.66, "max_drawdown_pct": -11.5,
        "var_95_daily_pct": -1.8, "cvar_95_daily_pct": -2.5,
    },
}


@pytest.fixture()
def mock_portfolio_tool():
    with patch(
        "src.stock_analysis.web.routes.portfolio._tool._run",
        return_value=_GOOD_PORTFOLIO_RESULT,
    ) as m:
        yield m


@pytest.fixture()
def mock_portfolio_error():
    with patch(
        "src.stock_analysis.web.routes.portfolio._tool._run",
        return_value={"error": "Insufficient price data returned for the requested symbols"},
    ) as m:
        yield m


class TestPortfolioAnalyzeEndpoint:
    def test_valid_request_returns_200(self, mock_portfolio_tool):
        resp = client.post(
            "/api/portfolio/analyze",
            json={"symbols": ["AAPL", "MSFT"], "period": "1y", "risk_free_rate": 0.02},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbols"] == ["AAPL", "MSFT"]
        assert "correlation_matrix" in body
        assert "portfolio_metrics" in body

    def test_symbols_normalized_to_uppercase(self, mock_portfolio_tool):
        resp = client.post(
            "/api/portfolio/analyze",
            json={"symbols": ["aapl", "msft"]},
        )
        assert resp.status_code == 200
        _args, _kwargs = mock_portfolio_tool.call_args
        assert _args[0] == ["AAPL", "MSFT"]

    def test_tool_error_returns_400(self, mock_portfolio_error):
        resp = client.post(
            "/api/portfolio/analyze",
            json={"symbols": ["AAPL", "MSFT"]},
        )
        assert resp.status_code == 400
        assert "Insufficient" in resp.json()["detail"]

    def test_too_few_symbols_422(self):
        resp = client.post("/api/portfolio/analyze", json={"symbols": ["AAPL"]})
        assert resp.status_code == 422

    def test_too_many_symbols_422(self):
        symbols = [f"S{i:02d}" for i in range(21)]
        resp = client.post("/api/portfolio/analyze", json={"symbols": symbols})
        assert resp.status_code == 422

    def test_invalid_symbol_in_list_422(self):
        resp = client.post(
            "/api/portfolio/analyze",
            json={"symbols": ["AAPL", "../evil"]},
        )
        assert resp.status_code == 422

    def test_custom_period_accepted(self, mock_portfolio_tool):
        resp = client.post(
            "/api/portfolio/analyze",
            json={"symbols": ["AAPL", "MSFT"], "period": "3y"},
        )
        assert resp.status_code == 200

    def test_risk_free_rate_out_of_range_422(self):
        resp = client.post(
            "/api/portfolio/analyze",
            json={"symbols": ["AAPL", "MSFT"], "risk_free_rate": 0.5},
        )
        assert resp.status_code == 422

    def test_defaults_applied(self, mock_portfolio_tool):
        resp = client.post("/api/portfolio/analyze", json={"symbols": ["AAPL", "MSFT"]})
        assert resp.status_code == 200
        _args, _kwargs = mock_portfolio_tool.call_args
        assert _args[1] == "1y"
        assert _args[2] == pytest.approx(0.02)

    def test_custom_weights_are_forwarded(self, mock_portfolio_tool):
        weights = {"AAPL": 0.7, "MSFT": 0.3}
        resp = client.post(
            "/api/portfolio/analyze",
            json={"symbols": ["AAPL", "MSFT"], "weights": weights},
        )
        assert resp.status_code == 200
        _args, _kwargs = mock_portfolio_tool.call_args
        assert _args[3] == weights

    def test_weights_must_match_symbols(self):
        resp = client.post(
            "/api/portfolio/analyze",
            json={"symbols": ["AAPL", "MSFT"], "weights": {"AAPL": 1.0}},
        )
        assert resp.status_code == 422


# ── Watchlist ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    """Redirect db to a fresh SQLite file per test; also reset the init flag."""
    from src.stock_analysis.web import db as db_mod

    db_path = tmp_path / "watchlist.db"
    monkeypatch.setattr(db_mod, "_db_path", lambda: db_path)
    monkeypatch.setattr(db_mod, "_initialized", False)
    yield


class TestWatchlistEndpoints:
    def test_list_empty_on_fresh_db(self):
        resp = client.get("/api/watchlist")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_add_symbol_returns_201(self):
        resp = client.post("/api/watchlist", json={"symbol": "AAPL", "notes": "test"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["symbol"] == "AAPL"
        assert body["notes"] == "test"
        assert "added_at" in body

    def test_add_normalizes_to_uppercase(self):
        resp = client.post("/api/watchlist", json={"symbol": "aapl"})
        assert resp.status_code == 201
        assert resp.json()["symbol"] == "AAPL"

    def test_add_invalid_symbol_400(self):
        resp = client.post("/api/watchlist", json={"symbol": "../bad"})
        assert resp.status_code == 422

    def test_add_duplicate_returns_409(self):
        client.post("/api/watchlist", json={"symbol": "AAPL"})
        resp = client.post("/api/watchlist", json={"symbol": "AAPL"})
        assert resp.status_code == 409

    def test_list_shows_added_symbol(self):
        client.post("/api/watchlist", json={"symbol": "MSFT", "notes": "cloud"})
        items = client.get("/api/watchlist").json()["items"]
        assert len(items) == 1
        assert items[0]["symbol"] == "MSFT"
        assert items[0]["notes"] == "cloud"

    def test_delete_existing_symbol_returns_204(self):
        client.post("/api/watchlist", json={"symbol": "NVDA"})
        resp = client.delete("/api/watchlist/NVDA")
        assert resp.status_code == 204

    def test_delete_removes_from_list(self):
        client.post("/api/watchlist", json={"symbol": "NVDA"})
        client.delete("/api/watchlist/NVDA")
        items = client.get("/api/watchlist").json()["items"]
        assert all(it["symbol"] != "NVDA" for it in items)

    def test_delete_nonexistent_returns_404(self):
        resp = client.delete("/api/watchlist/ZZZZ")
        assert resp.status_code == 404

    def test_delete_normalizes_symbol_case(self):
        client.post("/api/watchlist", json={"symbol": "TSLA"})
        resp = client.delete("/api/watchlist/tsla")
        assert resp.status_code == 204

    def test_list_ordered_by_added_at_desc(self):
        for sym in ["AAPL", "MSFT", "GOOGL"]:
            client.post("/api/watchlist", json={"symbol": sym})
        items = client.get("/api/watchlist").json()["items"]
        syms = [it["symbol"] for it in items]
        # added_at DESC means GOOGL (last added) comes first
        assert syms[0] == "GOOGL"
        assert syms[-1] == "AAPL"
