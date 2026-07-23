"""Tests for recommendation-history capture: live capture (jobs.py), backfill
from pre-existing report snapshots (reports_index.py), and the read endpoint
(routes/results.py). This is the raw series a future "was the advisor right?"
scorecard is built from."""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from src.stock_analysis.config import settings as settings_mod
from src.stock_analysis.web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _temp_reports(monkeypatch, tmp_path):
    from src.stock_analysis.web import db as db_mod

    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))
    monkeypatch.setattr(settings_mod.settings, "data_output_dir", str(tmp_path / "data"))
    monkeypatch.setattr(db_mod, "_initialized", False)
    yield tmp_path


def _seed(root, sym, *, prev=False, current=True, price=100.0):
    d = root / sym
    d.mkdir(parents=True, exist_ok=True)
    if prev:
        # Written first so its mtime predates the current snapshot's — mirrors
        # reality, where `prev` is the older run's file (archived via
        # shutil.copy2 before the new run overwrites `current`), and avoids
        # both landing in the same one-second timestamp bucket in this test.
        p = d / f"{sym}_investment_recommendation_prev.json"
        p.write_text(json.dumps({
            "recommendation": "Hold", "target_price": 110.0, "stop_loss": 85.0, "confidence": 0.6,
        }), encoding="utf-8")
        old = time.time() - 3600
        os.utime(p, (old, old))
    if current:
        (d / f"{sym}_investment_recommendation.json").write_text(json.dumps({
            "recommendation": "Buy", "target_price": 130.0, "stop_loss": 90.0, "confidence": 0.8,
        }), encoding="utf-8")
    (d / f"{sym}_chart_data.json").write_text(json.dumps({
        "key_stats": {"current_price": price},
    }), encoding="utf-8")


class TestBackfill:
    def test_backfills_current_snapshot(self, _temp_reports):
        from src.stock_analysis.web.reports_index import backfill_rec_history

        _seed(_temp_reports, "AAPL")
        count = backfill_rec_history()
        assert count == 1

        from src.stock_analysis.web import db
        rows = db.list_rec_history("AAPL")
        assert len(rows) == 1
        assert rows[0]["recommendation"] == "Buy"
        assert rows[0]["price_at_rec"] == 100.0

    def test_backfills_both_current_and_prev(self, _temp_reports):
        from src.stock_analysis.web.reports_index import backfill_rec_history

        _seed(_temp_reports, "AAPL", prev=True)
        count = backfill_rec_history()
        assert count == 2

        from src.stock_analysis.web import db
        rows = db.list_rec_history("AAPL")
        assert len(rows) == 2
        recs = {r["recommendation"] for r in rows}
        assert recs == {"Buy", "Hold"}
        # Only the current snapshot's price is known.
        prev_row = next(r for r in rows if r["recommendation"] == "Hold")
        assert prev_row["price_at_rec"] is None

    def test_backfill_is_idempotent(self, _temp_reports):
        from src.stock_analysis.web.reports_index import backfill_rec_history

        _seed(_temp_reports, "AAPL", prev=True)
        backfill_rec_history()
        backfill_rec_history()  # second pass must not duplicate rows

        from src.stock_analysis.web import db
        assert len(db.list_rec_history("AAPL")) == 2

    def test_missing_reports_root_is_a_noop(self, tmp_path, monkeypatch):
        from src.stock_analysis.web.reports_index import backfill_rec_history

        monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path / "nope"))
        assert backfill_rec_history() == 0

    def test_symbol_with_no_recommendation_files_contributes_nothing(self, _temp_reports):
        from src.stock_analysis.web.reports_index import backfill_rec_history

        (_temp_reports / "EMPTY").mkdir()
        assert backfill_rec_history() == 0


class TestRecHistoryEndpoint:
    def test_invalid_symbol_400(self, _temp_reports):
        r = client.get("/api/reports/AAPL$/rec-history")
        assert r.status_code == 400

    def test_empty_history_returns_empty_list(self, _temp_reports):
        r = client.get("/api/reports/AAPL/rec-history")
        assert r.status_code == 200
        assert r.json() == {"symbol": "AAPL", "items": []}

    def test_returns_backfilled_history_oldest_first(self, _temp_reports):
        from src.stock_analysis.web.reports_index import backfill_rec_history

        _seed(_temp_reports, "AAPL", prev=True)
        backfill_rec_history()

        r = client.get("/api/reports/AAPL/rec-history")
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"] == "AAPL"
        assert len(body["items"]) == 2
        # oldest first — both files share nearly the same mtime, but the
        # ordering contract itself is what matters here.
        assert {it["recommendation"] for it in body["items"]} == {"Buy", "Hold"}


class TestLiveCaptureOnJobCompletion:
    """JobManager._capture_rec_history (wired into _post_run_alerts_and_history)
    must append a rec_history row whenever a job completes with a recommendation."""

    def test_capture_rec_history_writes_a_row(self, _temp_reports):
        from src.stock_analysis.web import db
        from src.stock_analysis.web.jobs import Job, manager

        job = Job(
            id="j1", symbol="MSFT", depth="standard", asset_type="stock",
            use_cache=True, state="completed", finished_at="2026-07-23T10:00:00",
        )
        rec = {"recommendation": "Sell", "target_price": 300.0, "stop_loss": 250.0, "confidence": 0.55}
        manager._capture_rec_history(job, rec)

        rows = db.list_rec_history("MSFT")
        assert len(rows) == 1
        assert rows[0]["recommendation"] == "Sell"
        assert rows[0]["recorded_at"] == "2026-07-23T10:00:00"

    def test_capture_rec_history_reads_price_from_chart_data(self, _temp_reports):
        from src.stock_analysis.web import _paths, db
        from src.stock_analysis.web.jobs import Job, manager

        d = _temp_reports / "MSFT"
        d.mkdir(parents=True, exist_ok=True)
        (d / "MSFT_chart_data.json").write_text(
            json.dumps({"key_stats": {"current_price": 305.5}}), encoding="utf-8"
        )
        job = Job(
            id="j1", symbol="MSFT", depth="standard", asset_type="stock",
            use_cache=True, state="completed", finished_at="2026-07-23T10:00:00",
        )
        manager._capture_rec_history(job, {"recommendation": "Buy"})

        rows = db.list_rec_history("MSFT")
        assert rows[0]["price_at_rec"] == 305.5

    def test_capture_rec_history_never_raises_on_bad_input(self, _temp_reports):
        from src.stock_analysis.web.jobs import Job, manager

        job = Job(id="j1", symbol="MSFT", depth="standard", asset_type="stock", use_cache=True)
        manager._capture_rec_history(job, {"target_price": "not-a-number"})  # must not raise
