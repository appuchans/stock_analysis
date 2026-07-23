"""Tests for the consolidated SQLite data layer (web/db.py) and job recovery."""

import pytest


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    """Redirect the DB to a fresh SQLite file per test."""
    from src.stock_analysis.web import db as db_mod

    monkeypatch.setattr(db_mod, "_db_path", lambda: tmp_path / "app.db")
    monkeypatch.setattr(db_mod, "_initialized", False)
    yield


class TestWatchlistTable:
    def test_add_and_list(self):
        from src.stock_analysis.web import db

        assert db.add_symbol("AAPL", "core position") is True
        rows = db.list_symbols()
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["notes"] == "core position"

    def test_add_duplicate_returns_false(self):
        from src.stock_analysis.web import db

        db.add_symbol("AAPL")
        assert db.add_symbol("AAPL") is False

    def test_remove_symbol(self):
        from src.stock_analysis.web import db

        db.add_symbol("AAPL")
        assert db.remove_symbol("AAPL") is True
        assert db.symbol_exists("AAPL") is False


class TestJobsTable:
    def test_upsert_then_update(self):
        from src.stock_analysis.web import db

        job = {
            "id": "j1", "symbol": "AAPL", "depth": "standard", "asset_type": "stock",
            "use_cache": 1, "origin": "manual", "state": "queued", "stage": None,
            "error": None, "company_name": None, "progress": 0.0, "llm_calls": 0,
            "total_tokens": 0, "created_at": "2026-01-01T00:00:00", "started_at": None,
            "finished_at": None,
        }
        db.upsert_job(job)
        job["state"] = "completed"
        job["progress"] = 1.0
        db.upsert_job(job)
        rows = db.list_jobs()
        assert len(rows) == 1
        assert rows[0]["state"] == "completed"
        assert rows[0]["progress"] == 1.0

    def test_queued_jobs_filters_by_state(self):
        from src.stock_analysis.web import db

        for i, state in enumerate(["queued", "running", "queued", "completed"]):
            db.upsert_job({
                "id": f"j{i}", "symbol": "AAPL", "depth": "standard", "asset_type": "stock",
                "use_cache": 1, "origin": "manual", "state": state, "stage": None,
                "error": None, "company_name": None, "progress": 0.0, "llm_calls": 0,
                "total_tokens": 0, "created_at": f"2026-01-01T00:0{i}:00", "started_at": None,
                "finished_at": None,
            })
        queued = db.queued_jobs()
        assert {r["id"] for r in queued} == {"j0", "j2"}

    def test_mark_orphaned_running(self):
        from src.stock_analysis.web import db

        db.upsert_job({
            "id": "j1", "symbol": "AAPL", "depth": "standard", "asset_type": "stock",
            "use_cache": 1, "origin": "manual", "state": "running", "stage": None,
            "error": None, "company_name": None, "progress": 0.5, "llm_calls": 0,
            "total_tokens": 0, "created_at": "2026-01-01T00:00:00", "started_at": None,
            "finished_at": None,
        })
        count = db.mark_orphaned_running()
        assert count == 1
        assert db.list_jobs()[0]["state"] == "interrupted"


class TestRecHistoryTable:
    def test_record_and_list(self):
        from src.stock_analysis.web import db

        db.record_recommendation(
            symbol="AAPL", recorded_at="2026-01-01T00:00:00", recommendation="Buy",
            target_price=250.0, stop_loss=180.0, confidence=0.8, price_at_rec=200.0,
        )
        rows = db.list_rec_history("AAPL")
        assert len(rows) == 1
        assert rows[0]["recommendation"] == "Buy"
        assert rows[0]["target_price"] == 250.0

    def test_duplicate_timestamp_is_ignored(self):
        from src.stock_analysis.web import db

        for _ in range(2):
            db.record_recommendation(
                symbol="AAPL", recorded_at="2026-01-01T00:00:00", recommendation="Buy",
                target_price=250.0, stop_loss=180.0, confidence=0.8, price_at_rec=200.0,
            )
        assert len(db.list_rec_history("AAPL")) == 1


class TestAlertsLogTable:
    def test_append_and_list_newest_first(self):
        from src.stock_analysis.web import db

        db.append_alert({"symbol": "AAPL", "fired_at": "2026-01-01T00:00:00", "reason": "flip"})
        db.append_alert({"symbol": "MSFT", "fired_at": "2026-01-02T00:00:00", "reason": "drop"})
        rows = db.list_alerts()
        assert rows[0]["symbol"] == "MSFT"
        assert rows[1]["symbol"] == "AAPL"


class TestSettingsKV:
    def test_get_missing_returns_none(self):
        from src.stock_analysis.web import db

        assert db.get_setting("alert_email") is None

    def test_set_then_get(self):
        from src.stock_analysis.web import db

        db.set_setting("alert_email", "me@example.com")
        assert db.get_setting("alert_email") == "me@example.com"

    def test_set_overwrites(self):
        from src.stock_analysis.web import db

        db.set_setting("alert_email", "a@example.com")
        db.set_setting("alert_email", "b@example.com")
        assert db.get_setting("alert_email") == "b@example.com"
        assert db.all_settings() == {"alert_email": "b@example.com"}


class TestJobRecovery:
    def test_recover_reenqueues_queued_jobs_and_flags_running_as_interrupted(self, monkeypatch):
        from src.stock_analysis.web import db
        from src.stock_analysis.web.jobs import JobManager

        db.upsert_job({
            "id": "stale-running", "symbol": "MSFT", "depth": "standard", "asset_type": "stock",
            "use_cache": 1, "origin": "manual", "state": "running", "stage": None,
            "error": None, "company_name": None, "progress": 0.3, "llm_calls": 0,
            "total_tokens": 0, "created_at": "2026-01-01T00:00:00", "started_at": None,
            "finished_at": None,
        })
        db.upsert_job({
            "id": "stale-queued", "symbol": "GOOGL", "depth": "quick", "asset_type": "stock",
            "use_cache": 1, "origin": "scheduled", "state": "queued", "stage": None,
            "error": None, "company_name": None, "progress": 0.0, "llm_calls": 0,
            "total_tokens": 0, "created_at": "2026-01-01T00:01:00", "started_at": None,
            "finished_at": None,
        })

        # Block the freshly re-enqueued job's actual run so we can inspect
        # queue state without waiting for a real analysis.
        import threading

        gate = threading.Event()

        class _BlockingApp:
            def __init__(self, *a, **k):
                pass

            def analyze_stock(self, symbol, **k):
                gate.wait(timeout=5)
                return {"status": "completed", "token_usage": {}, "llm_calls": 0}

        monkeypatch.setattr("src.stock_analysis.main.StockAnalysisApp", _BlockingApp)
        monkeypatch.setattr(
            "src.stock_analysis.tools.free_data_collection.resolve_symbol",
            lambda symbol: {"name": f"{symbol} Inc.", "asset_type": "stock"},
        )

        mgr = JobManager()
        mgr.recover()

        # The stale "running" row (from a process that died mid-run) is
        # flagged interrupted and never re-run.
        msft_row = next(r for r in db.list_jobs() if r["symbol"] == "MSFT")
        assert msft_row["state"] == "interrupted"

        # The GOOGL job was re-enqueued as a brand-new in-memory job.
        import time

        deadline = time.time() + 2.0
        found = False
        while time.time() < deadline:
            if any(j.symbol == "GOOGL" and j.origin == "scheduled" for j in mgr._jobs.values()):
                found = True
                break
            time.sleep(0.02)
        assert found
        gate.set()

    def test_recover_is_idempotent(self):
        from src.stock_analysis.web.jobs import JobManager

        mgr = JobManager()
        mgr.recover()
        mgr.recover()  # second call must be a no-op, not re-enqueue anything
        assert mgr._recovered is True
