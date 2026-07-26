"""Tests for POST/GET/DELETE /api/portfolio/transactions, CSV import, and
GET /api/portfolio/positions."""

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


class TestTransactionEndpoints:
    def test_create_and_list_transaction(self):
        resp = client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "buy", "qty": 10, "price": 150.0, "date": "2026-01-01",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["symbol"] == "AAPL"
        assert body["qty"] == 10

        listed = client.get("/api/portfolio/transactions").json()
        assert len(listed) == 1

    def test_create_normalizes_symbol(self):
        resp = client.post("/api/portfolio/transactions", json={
            "symbol": "aapl", "side": "buy", "qty": 10, "price": 150.0, "date": "2026-01-01",
        })
        assert resp.json()["symbol"] == "AAPL"

    def test_create_invalid_symbol_422(self):
        resp = client.post("/api/portfolio/transactions", json={
            "symbol": "../evil", "side": "buy", "qty": 10, "price": 150.0, "date": "2026-01-01",
        })
        assert resp.status_code == 422

    def test_create_zero_qty_422(self):
        resp = client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "buy", "qty": 0, "price": 150.0, "date": "2026-01-01",
        })
        assert resp.status_code == 422

    def test_create_invalid_date_422(self):
        resp = client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "buy", "qty": 10, "price": 150.0, "date": "not-a-date",
        })
        assert resp.status_code == 422

    def test_create_invalid_side_422(self):
        resp = client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "hold", "qty": 10, "price": 150.0, "date": "2026-01-01",
        })
        assert resp.status_code == 422

    def test_delete_transaction(self):
        row = client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "buy", "qty": 10, "price": 150.0, "date": "2026-01-01",
        }).json()
        resp = client.delete(f"/api/portfolio/transactions/{row['id']}")
        assert resp.status_code == 204
        assert client.get("/api/portfolio/transactions").json() == []

    def test_delete_unknown_transaction_404(self):
        resp = client.delete("/api/portfolio/transactions/999999")
        assert resp.status_code == 404


class TestCSVImport:
    def test_import_valid_csv(self):
        csv_text = "date,symbol,side,qty,price\n2026-01-01,AAPL,buy,10,150.0\n2026-01-02,MSFT,buy,5,300.0\n"
        resp = client.post("/api/portfolio/transactions/import", json={"csv": csv_text})
        assert resp.status_code == 200
        assert resp.json()["imported"] == 2
        assert len(client.get("/api/portfolio/transactions").json()) == 2

    def test_import_malformed_csv_422(self):
        resp = client.post("/api/portfolio/transactions/import", json={"csv": "not,a,valid,header\n"})
        assert resp.status_code == 422

    def test_import_empty_csv_422(self):
        resp = client.post("/api/portfolio/transactions/import", json={"csv": "date,symbol,side,qty,price\n"})
        assert resp.status_code == 422


class TestPositionsEndpoint:
    def test_empty_transactions_returns_empty_positions(self):
        resp = client.get("/api/portfolio/positions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_positions_reflect_transactions(self):
        client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "buy", "qty": 10, "price": 150.0, "date": "2026-01-01",
        })
        resp = client.get("/api/portfolio/positions")
        body = resp.json()
        assert len(body) == 1
        assert body[0]["symbol"] == "AAPL"
        assert body[0]["qty"] == 10
        assert body[0]["avg_cost"] == 150.0

    def test_fully_closed_position_is_excluded(self):
        client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "buy", "qty": 10, "price": 150.0, "date": "2026-01-01",
        })
        client.post("/api/portfolio/transactions", json={
            "symbol": "AAPL", "side": "sell", "qty": 10, "price": 160.0, "date": "2026-02-01",
        })
        resp = client.get("/api/portfolio/positions")
        assert resp.json() == []
