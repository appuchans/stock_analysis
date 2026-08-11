"""Tests for web/rules.py: rule creation, cooldown, price-rule evaluation
(single symbol and batch), and post-run recommendation-based rules."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    from src.stock_analysis.web import db as db_mod

    monkeypatch.setattr(db_mod, "_db_path", lambda: tmp_path / "app.db")
    monkeypatch.setattr(db_mod, "_initialized", False)
    yield


@pytest.fixture(autouse=True)
def _no_real_dispatch(monkeypatch):
    """Never actually send email/webhooks from tests."""
    from src.stock_analysis.web import alerts

    monkeypatch.setattr(alerts, "_send_email", lambda *a, **k: None)
    monkeypatch.setattr(alerts, "_send_webhook", lambda *a, **k: None)


class TestCreateRule:
    def test_create_rule_persists(self):
        from src.stock_analysis.web import db, rules

        row = rules.create_rule("AAPL", "price_above", threshold=200.0)
        assert row["symbol"] == "AAPL"
        assert db.list_rules("AAPL")[0]["threshold"] == 200.0


class TestOffCooldown:
    def test_never_fired_is_off_cooldown(self):
        from src.stock_analysis.web.rules import _off_cooldown

        assert _off_cooldown({"last_fired_at": None, "cooldown_min": 60}) is True

    def test_recently_fired_is_on_cooldown(self):
        from src.stock_analysis.web.rules import _off_cooldown

        now = datetime.now(timezone.utc).isoformat()
        assert _off_cooldown({"last_fired_at": now, "cooldown_min": 60}) is False

    def test_expired_cooldown_is_off_cooldown(self):
        from src.stock_analysis.web.rules import _off_cooldown

        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        assert _off_cooldown({"last_fired_at": old, "cooldown_min": 60}) is True


class TestEvaluatePriceRulesForSymbol:
    def test_price_above_fires_when_crossed(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "price_above", threshold=150.0)
        rules.evaluate_price_rules_for_symbol("AAPL", quote={"price": 155.0})
        log = db.list_alerts()
        assert len(log) == 1
        assert "155" in log[0]["reason"]

    def test_price_above_does_not_fire_when_below_threshold(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "price_above", threshold=150.0)
        rules.evaluate_price_rules_for_symbol("AAPL", quote={"price": 100.0})
        assert db.list_alerts() == []

    def test_price_below_fires_when_crossed(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "price_below", threshold=100.0)
        rules.evaluate_price_rules_for_symbol("AAPL", quote={"price": 90.0})
        assert len(db.list_alerts()) == 1

    def test_pct_move_day_fires_on_large_move(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "pct_move_day", threshold=5.0)
        rules.evaluate_price_rules_for_symbol(
            "AAPL", quote={"price": 100.0, "change_pct": -6.2}
        )
        assert len(db.list_alerts()) == 1

    def test_disabled_rule_never_fires(self):
        from src.stock_analysis.web import db, rules

        row = rules.create_rule("AAPL", "price_above", threshold=1.0)
        db.set_rule_enabled(row["id"], False)
        rules.evaluate_price_rules_for_symbol("AAPL", quote={"price": 1000.0})
        assert db.list_alerts() == []

    def test_cooldown_suppresses_repeat_fire(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "price_above", threshold=150.0, cooldown_min=60)
        rules.evaluate_price_rules_for_symbol("AAPL", quote={"price": 155.0})
        rules.evaluate_price_rules_for_symbol("AAPL", quote={"price": 160.0})
        assert len(db.list_alerts()) == 1  # second fire suppressed by cooldown

    def test_missing_price_is_a_noop(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "price_above", threshold=150.0)
        rules.evaluate_price_rules_for_symbol("AAPL", quote={})
        assert db.list_alerts() == []

    def test_no_rules_for_symbol_short_circuits_without_quote_fetch(self, monkeypatch):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import rules

        def _should_not_be_called(symbol):
            raise AssertionError("no rules exist — must not fetch a quote")

        monkeypatch.setattr(router_mod.ROUTER, "get_quote", _should_not_be_called)
        rules.evaluate_price_rules_for_symbol("AAPL")  # no rules created


class TestEvaluateAllPriceRules:
    def test_no_price_rules_returns_zero_without_network(self, monkeypatch):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import rules

        monkeypatch.setattr(
            router_mod.ROUTER,
            "get_batch_quotes",
            lambda syms: (_ for _ in ()).throw(AssertionError("must not be called")),
        )
        assert rules.evaluate_all_price_rules() == 0

    def test_uses_batch_quotes_for_all_rule_symbols(self, monkeypatch):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "price_above", threshold=100.0)
        rules.create_rule("MSFT", "price_above", threshold=200.0)
        monkeypatch.setattr(
            router_mod.ROUTER,
            "get_batch_quotes",
            lambda syms: {
                "AAPL": {"price": 150.0},
                "MSFT": {"price": 250.0},
            },
        )
        count = rules.evaluate_all_price_rules()
        assert count == 2
        assert len(db.list_alerts()) == 2

    def test_falls_back_to_get_quote_when_symbol_missing_from_batch(self, monkeypatch):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "price_above", threshold=100.0)
        monkeypatch.setattr(router_mod.ROUTER, "get_batch_quotes", lambda syms: {})
        monkeypatch.setattr(
            router_mod.ROUTER, "get_quote", lambda sym: {"price": 150.0}
        )
        rules.evaluate_all_price_rules()
        assert len(db.list_alerts()) == 1


class TestEvaluatePostRunRules:
    def test_target_price_hit_fires(self, monkeypatch):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "target_price_hit")
        monkeypatch.setattr(
            router_mod.ROUTER, "get_quote", lambda sym: {"price": 210.0}
        )
        rules.evaluate_post_run_rules("AAPL", {"target_price": 200.0}, None)
        assert len(db.list_alerts()) == 1

    def test_target_price_not_yet_hit_does_not_fire(self, monkeypatch):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "target_price_hit")
        monkeypatch.setattr(
            router_mod.ROUTER, "get_quote", lambda sym: {"price": 150.0}
        )
        rules.evaluate_post_run_rules("AAPL", {"target_price": 200.0}, None)
        assert db.list_alerts() == []

    def test_stop_loss_hit_fires(self, monkeypatch):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "stop_loss_hit")
        monkeypatch.setattr(router_mod.ROUTER, "get_quote", lambda sym: {"price": 80.0})
        rules.evaluate_post_run_rules("AAPL", {"stop_loss": 90.0}, None)
        assert len(db.list_alerts()) == 1

    def test_custom_recommendation_changed_rule_fires(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "recommendation_changed")
        rules.evaluate_post_run_rules(
            "AAPL",
            {"recommendation": "Sell"},
            {"recommendation": "Buy"},
        )
        assert len(db.list_alerts()) == 1

    def test_custom_confidence_dropped_rule_with_threshold(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "confidence_dropped", threshold=0.1)
        rules.evaluate_post_run_rules(
            "AAPL",
            {"confidence": 0.65},
            {"confidence": 0.80},
        )
        assert len(db.list_alerts()) == 1

    def test_no_new_rec_is_a_noop(self):
        from src.stock_analysis.web import db, rules

        rules.create_rule("AAPL", "target_price_hit")
        rules.evaluate_post_run_rules("AAPL", None, {"recommendation": "Buy"})
        assert db.list_alerts() == []


class TestAlertsIntegration:
    """alerts.check_and_dispatch must additionally evaluate this symbol's
    rules — on top of, not instead of, the built-in flip/confidence triggers."""

    def test_check_and_dispatch_also_evaluates_rules(self, monkeypatch):
        from src.stock_analysis.tools.providers import router as router_mod
        from src.stock_analysis.web import alerts, db, rules

        rules.create_rule("AAPL", "target_price_hit")
        monkeypatch.setattr(
            router_mod.ROUTER, "get_quote", lambda sym: {"price": 999.0}
        )

        alerts.check_and_dispatch(
            "AAPL",
            {"recommendation": "Buy", "target_price": 500.0, "confidence": 0.7},
            {"recommendation": "Buy", "confidence": 0.7},
        )
        log = db.list_alerts()
        # Built-in triggers didn't fire (no flip, no confidence drop) but the
        # custom target_price_hit rule did.
        assert len(log) == 1
        assert "target" in log[0]["reason"]

    def test_rule_evaluation_failure_does_not_break_built_in_dispatch(
        self, monkeypatch
    ):
        from src.stock_analysis.web import alerts, db
        from src.stock_analysis.web import rules as rules_mod

        monkeypatch.setattr(
            rules_mod,
            "evaluate_post_run_rules",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        alerts.check_and_dispatch(
            "AAPL",
            {"recommendation": "Sell", "confidence": 0.5},
            {"recommendation": "Buy", "confidence": 0.5},
        )
        log = db.list_alerts()
        assert len(log) == 1
        assert "recommendation changed" in log[0]["reason"]
