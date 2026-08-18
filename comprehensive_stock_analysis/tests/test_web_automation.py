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


class TestEarningsWithinDaysRule:
    """This rule type was accepted by the API and shown as active while having
    no evaluator at all — it could never fire, and nothing reported that."""

    def _rule(self, threshold=7, last_fired=None):
        return {
            "id": 1,
            "symbol": "AAPL",
            "rule_type": "earnings_within_days",
            "threshold": threshold,
            "enabled": 1,
            "cooldown_min": 0,
            "last_fired_at": last_fired,
        }

    def _patch(self, monkeypatch, rule, earnings_date):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import rules as rules_mod

        monkeypatch.setattr(rules_mod.db, "list_rules", lambda symbol=None: [rule])
        monkeypatch.setattr(
            router_mod.ROUTER,
            "get_calendar",
            lambda s: {"next_earnings": {"date": earnings_date}} if earnings_date else {},
        )
        fired = []
        monkeypatch.setattr(
            rules_mod, "_dispatch", lambda sym, r, reason: fired.append(reason)
        )
        return fired, rules_mod

    def test_fires_when_earnings_are_inside_the_window(self, monkeypatch):
        from datetime import date, timedelta

        soon = (date.today() + timedelta(days=3)).isoformat()
        fired, rules_mod = self._patch(monkeypatch, self._rule(threshold=7), soon)
        rules_mod.evaluate_calendar_rules_for_symbol("AAPL")
        assert len(fired) == 1
        assert "3 day" in fired[0]

    def test_does_not_fire_when_earnings_are_far_off(self, monkeypatch):
        from datetime import date, timedelta

        far = (date.today() + timedelta(days=40)).isoformat()
        fired, rules_mod = self._patch(monkeypatch, self._rule(threshold=7), far)
        rules_mod.evaluate_calendar_rules_for_symbol("AAPL")
        assert fired == []

    def test_does_not_fire_for_a_past_earnings_date(self, monkeypatch):
        from datetime import date, timedelta

        past = (date.today() - timedelta(days=2)).isoformat()
        fired, rules_mod = self._patch(monkeypatch, self._rule(), past)
        rules_mod.evaluate_calendar_rules_for_symbol("AAPL")
        assert fired == []

    def test_no_scheduled_earnings_is_silent(self, monkeypatch):
        """Normal between cycles, and always true for an ETF — not an alert."""
        fired, rules_mod = self._patch(monkeypatch, self._rule(), None)
        rules_mod.evaluate_calendar_rules_for_symbol("AAPL")
        assert fired == []

    def test_daily_cooldown_floor_prevents_realerting_every_poll(self, monkeypatch):
        """The window stays satisfied for days; a 0-minute cooldown would
        otherwise re-alert on every 15-minute poll."""
        from datetime import date, datetime, timedelta, timezone

        soon = (date.today() + timedelta(days=3)).isoformat()
        just_fired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        fired, rules_mod = self._patch(
            monkeypatch, self._rule(last_fired=just_fired), soon
        )
        rules_mod.evaluate_calendar_rules_for_symbol("AAPL")
        assert fired == []

    def test_rule_type_is_registered_so_the_poll_picks_it_up(self):
        from src.stock_analysis.web import rules as rules_mod

        assert "earnings_within_days" in rules_mod.CALENDAR_RULE_TYPES
