"""Job lifecycle: submit → run (in a worker thread) → completed/failed + 409."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from src.stock_analysis.web.app import app

client = TestClient(app)


def _poll(job_id, until=("completed", "failed"), timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in until:
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach {until} in time")


class _FakeApp:
    """Stand-in for StockAnalysisApp; canned result, optional blocking gate."""

    result = None
    gate = None  # threading.Event the run waits on before returning

    def __init__(self, *a, **k):
        pass

    def analyze_stock(self, symbol, **k):
        if _FakeApp.gate is not None:
            _FakeApp.gate.wait(timeout=5)
        return dict(_FakeApp.result, symbol=symbol)


@pytest.fixture(autouse=True)
def _isolate_reports(monkeypatch, tmp_path):
    # The worker persists a run-status marker and job/rec-history rows; keep
    # both out of the real reports dir and the real app.db.
    from src.stock_analysis.config import settings as settings_mod
    from src.stock_analysis.web import db as db_mod

    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))
    monkeypatch.setattr(settings_mod.settings, "data_output_dir", str(tmp_path))
    monkeypatch.setattr(db_mod, "_initialized", False)


@pytest.fixture(autouse=True)
def _patch_app(monkeypatch):
    monkeypatch.setattr("src.stock_analysis.main.StockAnalysisApp", _FakeApp)
    _FakeApp.gate = None
    _FakeApp.result = {
        "status": "completed",
        "report": "/tmp/x.html",
        "recommendation": {"recommendation": "Buy", "target_price": 250.0},
        "token_usage": {
            "total_tokens": 1234,
            "prompt_tokens": 1000,
            "completion_tokens": 234,
        },
        "llm_calls": 7,
    }
    yield


@pytest.fixture(autouse=True)
def _patch_resolve_symbol(monkeypatch):
    """Keep the pre-flight symbol check off the network and deterministic;
    invalid-symbol behavior is exercised separately via a per-test override."""
    monkeypatch.setattr(
        "src.stock_analysis.tools.free_data_collection.resolve_symbol",
        lambda symbol: {"name": f"{symbol} Inc.", "asset_type": "stock"},
    )
    yield


def test_completed_job_surfaces_result():
    r = client.post("/api/analyze", json={"symbol": "AAPL", "depth": "quick"})
    assert r.status_code == 202
    job = _poll(r.json()["job_id"])
    assert job["state"] == "completed"
    assert job["progress"] == 1.0
    assert job["result_ready"] is True
    assert job["token_usage"]["total_tokens"] == 1234
    assert job["llm_calls"] == 7
    assert job["recommendation"]["recommendation"] == "Buy"


def test_failed_job_surfaces_error():
    _FakeApp.result = {
        "status": "failed",
        "error": "boom",
        "token_usage": {},
        "llm_calls": 0,
    }
    job = _poll(client.post("/api/analyze", json={"symbol": "MSFT"}).json()["job_id"])
    assert job["state"] == "failed"
    assert job["error"] == "boom"


def test_completed_job_surfaces_company_name():
    job = _poll(
        client.post("/api/analyze", json={"symbol": "AAPL", "depth": "quick"}).json()[
            "job_id"
        ]
    )
    assert job["company_name"] == "AAPL Inc."


def test_invalid_symbol_fails_fast_without_running_the_flow(monkeypatch):
    """A symbol that doesn't resolve to a real security (resolve_symbol
    returns None) must fail before StockAnalysisApp.analyze_stock ever runs —
    otherwise a bogus ticker would burn a full flow producing garbage output."""
    monkeypatch.setattr(
        "src.stock_analysis.tools.free_data_collection.resolve_symbol",
        lambda symbol: None,
    )
    called = False

    def _should_not_run(self, symbol, **k):
        nonlocal called
        called = True
        return {"status": "completed"}

    monkeypatch.setattr(_FakeApp, "analyze_stock", _should_not_run)

    job = _poll(
        client.post("/api/analyze", json={"symbol": "ZZZINVALID"}).json()["job_id"]
    )
    assert job["state"] == "failed"
    assert "ZZZINVALID" in job["error"]
    assert job["company_name"] is None
    assert called is False


def test_cancel_marks_job_aborted(monkeypatch, tmp_path):
    # keep the status marker out of the real reports dir
    from src.stock_analysis.config import settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))

    # Genuine abort: analyze_stock stops short of completing (e.g. it caught
    # AnalysisAbortedError internally) so its result status is NOT
    # "completed" — this is what distinguishes a real abort from the
    # completed-despite-cancel race covered below.
    _FakeApp.result = {"status": "aborted", "token_usage": {}, "llm_calls": 3}
    _FakeApp.gate = threading.Event()
    job_id = client.post("/api/analyze", json={"symbol": "TSLA"}).json()["job_id"]
    # cancel while running — a still-"queued" job is now dropped without ever
    # calling analyze_stock (see test_cancel_queued_job_...), so wait past that
    # window to exercise the in-flight cancel path this test targets.
    _poll(job_id, until=("running",), timeout=2.0)
    c = client.post(f"/api/jobs/{job_id}/cancel")
    assert c.status_code == 200 and c.json()["state"] == "cancelling"
    _FakeApp.gate.set()  # let the (mock) run finish; worker honors cancel_requested
    job = _poll(job_id, until=("aborted", "completed", "failed"))
    assert job["state"] == "aborted"
    # a status marker was persisted for the history page
    assert (tmp_path / "TSLA" / "TSLA_run_status.json").exists()


def test_cancel_race_completed_result_is_not_mislabeled_aborted(monkeypatch, tmp_path):
    """Regression guard for the cancel/reset race: if analyze_stock finishes
    and returns status="completed" just as a cancel was requested (the run
    was already past its last abort-checkpoint), the job must be reported
    completed — never mislabeled "aborted" just because cancel_requested was
    set. The result's own status always wins over cancel_requested."""
    from src.stock_analysis.config import settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))

    # _patch_app's default _FakeApp.result already has status="completed".
    _FakeApp.gate = threading.Event()
    job_id = client.post("/api/analyze", json={"symbol": "TSLA"}).json()["job_id"]
    _poll(job_id, until=("running",), timeout=2.0)
    c = client.post(f"/api/jobs/{job_id}/cancel")
    assert c.status_code == 200 and c.json()["state"] == "cancelling"
    _FakeApp.gate.set()  # analyze_stock returns status="completed" despite the cancel
    job = _poll(job_id, until=("aborted", "completed", "failed"))
    assert job["state"] == "completed"
    assert job["result_ready"] is True


def test_live_view_exposes_activity():
    from src.stock_analysis.web import progress
    from src.stock_analysis.web.jobs import Job, manager

    job = Job(
        id="t1",
        symbol="AAPL",
        depth="standard",
        asset_type="auto",
        use_cache=True,
        state="running",
    )
    job.tracker = progress.StageTracker()
    job.tracker.set_stage("Synthesizing recommendation", 0.80)
    job.tracker.note("Risk Analysis · Yahoo Finance")
    view = manager.live_view(job)
    assert view["activity"] == "Risk Analysis · Yahoo Finance"
    assert view["stage"] == "Synthesizing recommendation"
    assert view["progress"] == 0.8


def test_stage_progresses_through_flow_and_is_monotonic():
    from src.stock_analysis.web import progress

    t = progress.StageTracker()
    progress.set_active(t)
    try:
        for method in (
            "collect_data",
            "standard_analysis",
            "synthesize_recommendation",
            "generate_report",
        ):
            progress._dispatch_stage(*progress._STAGE_MAP[method])
        assert t.snapshot() == ("Generating report", 0.92)
        # a stray earlier event must never move the bar backwards
        progress._dispatch_stage(*progress._STAGE_MAP["collect_data"])
        assert t.snapshot()[1] == 0.92
    finally:
        progress.set_active(None)


def test_task_label_falls_back_to_task_object_when_task_name_unset():
    """Regression: crewai's AgentExecutionStartedEvent never populates
    task_name (only ToolUsageStartedEvent does), which used to freeze the
    activity ticker on the last tool call once a stage — e.g. synthesis or
    report generation — ran an agent that never invokes a tool."""
    from src.stock_analysis.web.progress import _task_label

    class _FakeTask:
        name = "Investment Recommendation"

    class _FakeEvent:
        task_name = None
        task = _FakeTask()

    assert _task_label(_FakeEvent()) == "Investment Recommendation"


def test_cancel_unknown_job_404():
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_cancel_finished_job_409():
    job_id = client.post("/api/analyze", json={"symbol": "AAPL"}).json()["job_id"]
    _poll(job_id)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409


def test_concurrent_submit_is_queued_not_rejected_and_handler_is_nonblocking():
    """A second submission while one is active now queues (FIFO) instead of
    being rejected with 409 — the single-worker invariant still holds (only
    one _run executes at a time), but the caller doesn't have to retry."""
    _FakeApp.gate = threading.Event()
    first = client.post("/api/analyze", json={"symbol": "NVDA"})  # returns immediately
    assert first.status_code == 202
    # Worker is blocked in analyze_stock → job is active; a 2nd submit queues.
    second = client.post("/api/analyze", json={"symbol": "AMD"})
    assert second.status_code == 202
    second_id = second.json()["job_id"]
    # Status endpoint stays responsive while the run blocks.
    running = client.get(f"/api/jobs/{first.json()['job_id']}").json()
    assert running["state"] in ("queued", "running")
    queued = client.get(f"/api/jobs/{second_id}").json()
    assert queued["state"] == "queued"
    assert queued["queue_position"] >= 1
    _FakeApp.gate.set()  # release the worker so the first run completes
    done = _poll(first.json()["job_id"])
    assert done["state"] == "completed"
    # The queued second job now runs to completion in turn.
    second_done = _poll(second_id)
    assert second_done["state"] == "completed"


def test_coalescing_returns_existing_job_for_same_symbol():
    """Re-submitting the same symbol while it is already queued/running with an
    equal-or-deeper depth returns the existing job instead of enqueueing a
    duplicate — prevents pile-ups from double-clicks or scheduler overlap."""
    _FakeApp.gate = threading.Event()
    first = client.post("/api/analyze", json={"symbol": "NVDA", "depth": "standard"})
    dup = client.post("/api/analyze", json={"symbol": "NVDA", "depth": "quick"})
    assert dup.json()["job_id"] == first.json()["job_id"]
    _FakeApp.gate.set()
    _poll(first.json()["job_id"])


class TestWatchlistBatchAnalyze:
    """POST /api/watchlist/analyze must enqueue every symbol (not just the
    first) now that the queue can hold more than one job at a time."""

    @pytest.fixture(autouse=True)
    def _fresh_watchlist(self, monkeypatch, tmp_path):
        from src.stock_analysis.web import db as db_mod

        monkeypatch.setattr(db_mod, "_db_path", lambda: tmp_path / "app.db")
        monkeypatch.setattr(db_mod, "_initialized", False)

    def test_empty_watchlist_400(self):
        resp = client.post("/api/watchlist/analyze", json={})
        assert resp.status_code == 400

    def test_all_symbols_enqueued(self):
        for sym in ["AAPL", "MSFT", "GOOGL"]:
            client.post("/api/watchlist", json={"symbol": sym})
        _FakeApp.gate = threading.Event()
        resp = client.post("/api/watchlist/analyze", json={"depth": "quick"})
        assert resp.status_code == 202
        body = resp.json()
        assert sorted(body["queued"]) == ["AAPL", "GOOGL", "MSFT"]
        assert len(body["job_ids"]) == 3
        _FakeApp.gate.set()
        for job_id in body["job_ids"]:
            assert _poll(job_id)["state"] == "completed"

    def test_jobs_carry_watchlist_origin(self):
        client.post("/api/watchlist", json={"symbol": "AAPL"})
        _FakeApp.gate = threading.Event()
        resp = client.post("/api/watchlist/analyze", json={"depth": "quick"})
        job_id = resp.json()["job_ids"][0]
        assert client.get(f"/api/jobs/{job_id}").json()["origin"] == "watchlist"
        _FakeApp.gate.set()
        _poll(job_id)


def test_cancel_queued_job_removes_it_without_touching_active_run():
    _FakeApp.gate = threading.Event()
    first = client.post("/api/analyze", json={"symbol": "NVDA"})
    second = client.post("/api/analyze", json={"symbol": "AMD"})
    c = client.post(f"/api/jobs/{second.json()['job_id']}/cancel")
    assert c.status_code == 200
    cancelled = client.get(f"/api/jobs/{second.json()['job_id']}").json()
    assert cancelled["state"] == "aborted"
    _FakeApp.gate.set()
    done = _poll(first.json()["job_id"])
    assert done["state"] == "completed"


def test_refresh_while_running_queues_and_never_aborts_the_active_run():
    """A Refresh click (POST /api/analyze with use_cache=false) on a *different*
    symbol must queue behind the run in flight — never cancel it.

    The UI used to look like it cancelled the first run, because the progress
    card switched to the new job and stopped polling the old one. Guard the
    server contract the UI depends on: the in-flight job stays active and
    completes, and the refresh runs afterwards.
    """
    _FakeApp.gate = threading.Event()
    running = client.post("/api/analyze", json={"symbol": "NVDA"}).json()["job_id"]

    # Refresh a different symbol while NVDA is mid-run.
    refresh = client.post(
        "/api/analyze",
        json={"symbol": "AMD", "depth": "standard", "use_cache": False},
    )
    assert refresh.status_code == 202
    refresh_id = refresh.json()["job_id"]
    assert refresh_id != running

    # The active run is untouched: still active, not aborting, and it owns the
    # worker while the refresh waits its turn.
    active = client.get(f"/api/jobs/{running}").json()
    assert active["state"] in ("queued", "running")
    assert client.get("/api/jobs").json()["active_id"] == running
    queued = client.get(f"/api/jobs/{refresh_id}").json()
    assert queued["state"] == "queued"
    assert queued["queue_position"] >= 1

    _FakeApp.gate.set()
    assert _poll(running)["state"] == "completed"
    assert _poll(refresh_id)["state"] == "completed"


def test_resume_flag_reaches_the_analysis_app():
    """POST /api/analyze {resume:true} must reach StockAnalysisApp(resume=True).

    The Resume button on an incomplete history tile is the only thing that
    prevents re-paying for stages that already succeeded, so the flag has to
    survive every layer between the request and the flow.
    """
    seen = {}

    class _CapturingApp(_FakeApp):
        def __init__(self, *a, **k):
            seen.update(k)

    import src.stock_analysis.main as main_mod

    original = main_mod.StockAnalysisApp
    main_mod.StockAnalysisApp = _CapturingApp
    try:
        job_id = client.post(
            "/api/analyze",
            json={"symbol": "TSLA", "use_cache": False, "resume": True},
        ).json()["job_id"]
        _poll(job_id)
    finally:
        main_mod.StockAnalysisApp = original

    assert seen.get("resume") is True
    assert seen.get("use_data_cache") is False


def test_resume_defaults_false_for_a_plain_analysis():
    seen = {}

    class _CapturingApp(_FakeApp):
        def __init__(self, *a, **k):
            seen.update(k)

    import src.stock_analysis.main as main_mod

    original = main_mod.StockAnalysisApp
    main_mod.StockAnalysisApp = _CapturingApp
    try:
        job_id = client.post("/api/analyze", json={"symbol": "META"}).json()["job_id"]
        _poll(job_id)
    finally:
        main_mod.StockAnalysisApp = original

    assert seen.get("resume") is False


class TestRecentRunGuard:
    """A full analysis costs a full set of LLM calls and the data barely moves
    within a day, so an accidental Refresh minutes after a run is almost always
    a mistake. Only manual submissions hit this route — scheduled and watchlist
    runs call manager.submit directly, so they are exempt for free."""

    def _seed_completed(self, tmp_path, hours_ago, status="completed"):
        import json as _json
        from datetime import datetime, timedelta

        d = tmp_path / "AAPL"
        d.mkdir(parents=True, exist_ok=True)
        stamp = (datetime.now() - timedelta(hours=hours_ago)).isoformat(
            timespec="seconds"
        )
        (d / "AAPL_run_status.json").write_text(
            _json.dumps({"status": status, "finished_at": stamp}), encoding="utf-8"
        )

    def test_manual_rerun_within_the_window_is_refused(self, tmp_path):
        self._seed_completed(tmp_path, hours_ago=0.5)
        r = client.post("/api/analyze", json={"symbol": "AAPL"})
        assert r.status_code == 409
        assert "analyzed" in r.json()["detail"]

    def test_force_overrides_the_window(self, tmp_path):
        self._seed_completed(tmp_path, hours_ago=0.5)
        r = client.post("/api/analyze", json={"symbol": "AAPL", "force": True})
        assert r.status_code == 202
        _poll(r.json()["job_id"])

    def test_failed_run_can_be_retried_immediately(self, tmp_path):
        """Retrying a failure is exactly what a user should be able to do."""
        self._seed_completed(tmp_path, hours_ago=0.1, status="failed")
        r = client.post("/api/analyze", json={"symbol": "AAPL"})
        assert r.status_code == 202
        _poll(r.json()["job_id"])

    def test_scheduled_runs_bypass_the_route_entirely(self, tmp_path):
        from src.stock_analysis.web.jobs import manager

        self._seed_completed(tmp_path, hours_ago=0.1)
        job = manager.submit("AAPL", "standard", "auto", True, origin="scheduled")
        _poll(job.id)
