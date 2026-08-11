"""Tests for POST/GET/DELETE /api/schedules and /api/rules."""

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


class TestScheduleEndpoints:
    def test_create_and_list_schedule(self):
        resp = client.post(
            "/api/schedules", json={"target": "watchlist", "cron_expr": "0 18 * * 1-5"}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["target"] == "watchlist"
        assert body["enabled"] is True

        listed = client.get("/api/schedules").json()
        assert len(listed) == 1
        assert listed[0]["id"] == body["id"]

    def test_create_normalizes_symbol_target_uppercase(self):
        resp = client.post(
            "/api/schedules", json={"target": "aapl", "cron_expr": "0 * * * *"}
        )
        assert resp.status_code == 201
        assert resp.json()["target"] == "AAPL"

    def test_create_invalid_target_422(self):
        resp = client.post(
            "/api/schedules", json={"target": "../evil", "cron_expr": "0 * * * *"}
        )
        assert resp.status_code == 422

    def test_create_invalid_cron_422(self):
        resp = client.post(
            "/api/schedules", json={"target": "watchlist", "cron_expr": "garbage"}
        )
        assert resp.status_code == 422

    def test_toggle_schedule(self):
        row = client.post(
            "/api/schedules", json={"target": "AAPL", "cron_expr": "0 * * * *"}
        ).json()
        resp = client.post(
            f"/api/schedules/{row['id']}/toggle", params={"enabled": False}
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_toggle_unknown_schedule_404(self):
        resp = client.post("/api/schedules/nope/toggle", params={"enabled": False})
        assert resp.status_code == 404

    def test_delete_schedule(self):
        row = client.post(
            "/api/schedules", json={"target": "AAPL", "cron_expr": "0 * * * *"}
        ).json()
        resp = client.delete(f"/api/schedules/{row['id']}")
        assert resp.status_code == 204
        assert client.get("/api/schedules").json() == []

    def test_delete_unknown_schedule_404(self):
        resp = client.delete("/api/schedules/nope")
        assert resp.status_code == 404


class TestRuleEndpoints:
    def test_create_and_list_rule(self):
        resp = client.post(
            "/api/rules",
            json={
                "symbol": "AAPL",
                "rule_type": "price_above",
                "threshold": 200.0,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["symbol"] == "AAPL"
        assert body["threshold"] == 200.0

        listed = client.get("/api/rules").json()
        assert len(listed) == 1

    def test_create_price_rule_without_threshold_422(self):
        resp = client.post(
            "/api/rules", json={"symbol": "AAPL", "rule_type": "price_above"}
        )
        assert resp.status_code == 422

    def test_create_recommendation_changed_rule_without_threshold_ok(self):
        resp = client.post(
            "/api/rules",
            json={
                "symbol": "AAPL",
                "rule_type": "recommendation_changed",
            },
        )
        assert resp.status_code == 201

    def test_create_invalid_symbol_422(self):
        resp = client.post(
            "/api/rules",
            json={
                "symbol": "../evil",
                "rule_type": "recommendation_changed",
            },
        )
        assert resp.status_code == 422

    def test_create_invalid_rule_type_422(self):
        resp = client.post(
            "/api/rules", json={"symbol": "AAPL", "rule_type": "not_a_real_type"}
        )
        assert resp.status_code == 422

    def test_toggle_rule(self):
        row = client.post(
            "/api/rules",
            json={
                "symbol": "AAPL",
                "rule_type": "recommendation_changed",
            },
        ).json()
        resp = client.post(f"/api/rules/{row['id']}/toggle", params={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_toggle_unknown_rule_404(self):
        resp = client.post("/api/rules/nope/toggle", params={"enabled": False})
        assert resp.status_code == 404

    def test_delete_rule(self):
        row = client.post(
            "/api/rules",
            json={
                "symbol": "AAPL",
                "rule_type": "recommendation_changed",
            },
        ).json()
        resp = client.delete(f"/api/rules/{row['id']}")
        assert resp.status_code == 204
        assert client.get("/api/rules").json() == []

    def test_delete_unknown_rule_404(self):
        resp = client.delete("/api/rules/nope")
        assert resp.status_code == 404
