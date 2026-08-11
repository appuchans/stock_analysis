"""Tests for web/scheduler.py: cron validation, schedule CRUD, firing logic
(cost governor, monitor-mode data-only refresh, watchlist expansion), all
exercised directly (not by waiting on real APScheduler timing)."""

import pytest


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    from src.stock_analysis.web import db as db_mod

    monkeypatch.setattr(db_mod, "_db_path", lambda: tmp_path / "app.db")
    monkeypatch.setattr(db_mod, "_initialized", False)
    yield


class TestValidateCron:
    def test_valid_cron_does_not_raise(self):
        from src.stock_analysis.web.scheduler import validate_cron

        validate_cron("0 18 * * 1-5")  # must not raise

    def test_invalid_cron_raises_value_error(self):
        from src.stock_analysis.web.scheduler import validate_cron

        with pytest.raises(ValueError):
            validate_cron("not a cron expression")


class TestScheduleCRUD:
    def test_create_schedule_persists(self):
        from src.stock_analysis.web import scheduler

        row = scheduler.create_schedule(target="watchlist", cron_expr="0 18 * * 1-5")
        assert row["target"] == "watchlist"
        assert row["enabled"] is True
        assert scheduler.list_schedules()[0]["id"] == row["id"]

    def test_create_schedule_rejects_bad_cron(self):
        from src.stock_analysis.web import scheduler

        with pytest.raises(ValueError):
            scheduler.create_schedule(target="AAPL", cron_expr="garbage")

    def test_toggle_schedule_unknown_id_returns_false(self):
        from src.stock_analysis.web import scheduler

        assert scheduler.toggle_schedule("nope", False) is False

    def test_toggle_schedule_disables(self):
        from src.stock_analysis.web import scheduler

        row = scheduler.create_schedule(target="AAPL", cron_expr="0 * * * *")
        assert scheduler.toggle_schedule(row["id"], False) is True
        updated = scheduler.list_schedules()[0]
        # db.py returns raw SQLite ints (0/1), not coerced bools — bool
        # coercion happens at the schemas.py/API layer.
        assert not updated["enabled"]

    def test_remove_schedule(self):
        from src.stock_analysis.web import scheduler

        row = scheduler.create_schedule(target="AAPL", cron_expr="0 * * * *")
        assert scheduler.remove_schedule(row["id"]) is True
        assert scheduler.list_schedules() == []

    def test_remove_unknown_schedule_returns_false(self):
        from src.stock_analysis.web import scheduler

        assert scheduler.remove_schedule("nope") is False


class TestFireSchedule:
    def test_unknown_schedule_id_is_a_noop(self):
        from src.stock_analysis.web.scheduler import _fire_schedule

        _fire_schedule("nope")  # must not raise

    def test_disabled_schedule_does_not_fire(self, monkeypatch):
        from src.stock_analysis.web import db, scheduler

        row = scheduler.create_schedule(target="AAPL", cron_expr="0 * * * *")
        db.set_schedule_enabled(row["id"], False)
        called = []
        monkeypatch.setattr(
            scheduler, "_target_symbols", lambda t: called.append(t) or ["AAPL"]
        )
        scheduler._fire_schedule(row["id"])
        assert called == []

    def test_empty_watchlist_records_skipped(self):
        from src.stock_analysis.web import db, scheduler

        row = scheduler.create_schedule(target="watchlist", cron_expr="0 * * * *")
        scheduler._fire_schedule(row["id"])
        updated = db.get_schedule(row["id"])
        assert "skipped: no symbols" in updated["last_result"]

    def test_watchlist_target_expands_to_all_symbols(self, monkeypatch):
        from src.stock_analysis.web import db, scheduler

        db.add_symbol("AAPL")
        db.add_symbol("MSFT")
        row = scheduler.create_schedule(target="watchlist", cron_expr="0 * * * *")
        submitted = []

        # jobs.manager is imported lazily inside _fire_schedule; patch the
        # real module so that lazy import picks up the stub.
        import src.stock_analysis.web.jobs as jobs_mod

        monkeypatch.setattr(
            jobs_mod,
            "manager",
            type(
                "M",
                (),
                {
                    "submit": staticmethod(
                        lambda sym, depth, atype, cache, origin: submitted.append(sym)
                        or type("J", (), {"symbol": sym})()
                    )
                },
            )(),
        )

        scheduler._fire_schedule(row["id"])
        assert sorted(submitted) == ["AAPL", "MSFT"]

    def test_monitor_only_calls_refresh_data_only_not_manager_submit(self, monkeypatch):
        from src.stock_analysis.web import db, scheduler

        row = scheduler.create_schedule(
            target="AAPL", cron_expr="0 * * * *", monitor_only=True
        )
        refreshed = []
        monkeypatch.setattr(
            scheduler,
            "refresh_data_only",
            lambda sym, use_cache=False: refreshed.append(sym) or True,
        )
        monkeypatch.setattr(
            scheduler, "_evaluate_rules_after_refresh", lambda symbols: None
        )

        import src.stock_analysis.web.jobs as jobs_mod

        def _should_not_be_called(*a, **k):
            raise AssertionError("monitor_only schedules must not enqueue a real job")

        monkeypatch.setattr(
            jobs_mod,
            "manager",
            type("M", (), {"submit": staticmethod(_should_not_be_called)})(),
        )

        scheduler._fire_schedule(row["id"])
        assert refreshed == ["AAPL"]
        updated = db.get_schedule(row["id"])
        assert "monitor refresh: 1/1 ok" in updated["last_result"]

    def test_daily_cap_blocks_scheduled_submission(self, monkeypatch):
        from src.stock_analysis.web import db, scheduler

        db.set_setting("daily_llm_call_cap", "10")
        monkeypatch.setattr(db, "scheduled_llm_calls_today", lambda: 15)
        row = scheduler.create_schedule(target="AAPL", cron_expr="0 * * * *")

        import src.stock_analysis.web.jobs as jobs_mod

        def _should_not_be_called(*a, **k):
            raise AssertionError("cap should have blocked this submission")

        monkeypatch.setattr(
            jobs_mod,
            "manager",
            type("M", (), {"submit": staticmethod(_should_not_be_called)})(),
        )

        scheduler._fire_schedule(row["id"])
        updated = db.get_schedule(row["id"])
        assert "daily LLM call cap" in updated["last_result"]

    def test_daily_cap_does_not_block_when_under_cap(self, monkeypatch):
        from src.stock_analysis.web import db, scheduler

        db.set_setting("daily_llm_call_cap", "100")
        monkeypatch.setattr(db, "scheduled_llm_calls_today", lambda: 5)
        row = scheduler.create_schedule(target="AAPL", cron_expr="0 * * * *")

        import src.stock_analysis.web.jobs as jobs_mod

        submitted = []
        monkeypatch.setattr(
            jobs_mod,
            "manager",
            type(
                "M",
                (),
                {
                    "submit": staticmethod(
                        lambda sym, depth, atype, cache, origin: submitted.append(
                            (sym, origin)
                        )
                        or type("J", (), {"symbol": sym})()
                    )
                },
            )(),
        )
        scheduler._fire_schedule(row["id"])
        assert submitted == [("AAPL", "scheduled")]

    def test_no_cap_configured_never_blocks(self, monkeypatch):
        from src.stock_analysis.web import db, scheduler

        assert db.get_setting("daily_llm_call_cap") is None
        row = scheduler.create_schedule(target="AAPL", cron_expr="0 * * * *")

        import src.stock_analysis.web.jobs as jobs_mod

        submitted = []
        monkeypatch.setattr(
            jobs_mod,
            "manager",
            type(
                "M",
                (),
                {
                    "submit": staticmethod(
                        lambda sym, depth, atype, cache, origin: submitted.append(sym)
                        or type("J", (), {"symbol": sym})()
                    )
                },
            )(),
        )
        scheduler._fire_schedule(row["id"])
        assert submitted == ["AAPL"]


class TestRefreshDataOnly:
    def test_invalid_symbol_returns_false(self, monkeypatch):
        from src.stock_analysis.web import scheduler

        monkeypatch.setattr(
            "src.stock_analysis.tools.free_data_collection.resolve_symbol",
            lambda s: None,
        )
        assert scheduler.refresh_data_only("ZZZINVALID") is False

    def test_valid_symbol_calls_fetch_structured_not_kickoff(self, monkeypatch):
        from src.stock_analysis.web import scheduler

        monkeypatch.setattr(
            "src.stock_analysis.tools.free_data_collection.resolve_symbol",
            lambda s: {"name": "Apple Inc.", "asset_type": "stock"},
        )

        calls = {"fetch_structured": 0, "kickoff": 0}

        class _FakeFlow:
            def __init__(self, *a, **k):
                self.state = type("S", (), {})()

            def _fetch_structured(self):
                calls["fetch_structured"] += 1

            def kickoff(self, *a, **k):
                calls["kickoff"] += 1

        monkeypatch.setattr(
            "src.stock_analysis.crew.flow_crew.StockAnalysisFlow", _FakeFlow
        )
        assert scheduler.refresh_data_only("AAPL") is True
        assert calls == {"fetch_structured": 1, "kickoff": 0}

    def test_fetch_exception_returns_false(self, monkeypatch):
        from src.stock_analysis.web import scheduler

        monkeypatch.setattr(
            "src.stock_analysis.tools.free_data_collection.resolve_symbol",
            lambda s: {"name": "Apple Inc.", "asset_type": "stock"},
        )

        class _FakeFlow:
            def __init__(self, *a, **k):
                self.state = type("S", (), {})()

            def _fetch_structured(self):
                raise RuntimeError("network down")

        monkeypatch.setattr(
            "src.stock_analysis.crew.flow_crew.StockAnalysisFlow", _FakeFlow
        )
        assert scheduler.refresh_data_only("AAPL") is False


class TestSchedulerLifecycle:
    def test_start_is_idempotent_and_stop_cleans_up(self):
        from src.stock_analysis.web import scheduler

        try:
            scheduler.start()
            scheduler.start()  # second call must be a no-op, not raise
            assert scheduler._scheduler is not None
        finally:
            scheduler.stop()
        assert scheduler._scheduler is None

    def test_start_registers_enabled_schedules_and_quote_poll_job(self):
        from src.stock_analysis.web import scheduler

        scheduler.create_schedule(target="AAPL", cron_expr="0 * * * *")
        try:
            scheduler.start()
            job_ids = {j.id for j in scheduler._scheduler.get_jobs()}
            assert scheduler._QUOTE_POLL_JOB_ID in job_ids
        finally:
            scheduler.stop()
