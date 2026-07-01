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
    # The worker persists a run-status marker; keep it out of the real reports dir.
    from src.stock_analysis.config import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))


@pytest.fixture(autouse=True)
def _patch_app(monkeypatch):
    monkeypatch.setattr("src.stock_analysis.main.StockAnalysisApp", _FakeApp)
    _FakeApp.gate = None
    _FakeApp.result = {
        "status": "completed",
        "report": "/tmp/x.html",
        "recommendation": {"recommendation": "Buy", "target_price": 250.0},
        "token_usage": {"total_tokens": 1234, "prompt_tokens": 1000, "completion_tokens": 234},
        "llm_calls": 7,
    }
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
    _FakeApp.result = {"status": "failed", "error": "boom", "token_usage": {}, "llm_calls": 0}
    job = _poll(client.post("/api/analyze", json={"symbol": "MSFT"}).json()["job_id"])
    assert job["state"] == "failed"
    assert job["error"] == "boom"


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
    # cancel while running
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
    c = client.post(f"/api/jobs/{job_id}/cancel")
    assert c.status_code == 200 and c.json()["state"] == "cancelling"
    _FakeApp.gate.set()  # analyze_stock returns status="completed" despite the cancel
    job = _poll(job_id, until=("aborted", "completed", "failed"))
    assert job["state"] == "completed"
    assert job["result_ready"] is True


def test_live_view_exposes_activity():
    from src.stock_analysis.web import progress
    from src.stock_analysis.web.jobs import Job, manager

    job = Job(id="t1", symbol="AAPL", depth="standard", asset_type="auto", use_cache=True, state="running")
    job.tracker = progress.StageTracker(4)
    job.tracker.note("Risk Analyst · Yahoo Finance")
    assert manager.live_view(job)["activity"] == "Risk Analyst · Yahoo Finance"


def test_cancel_unknown_job_404():
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_cancel_finished_job_409():
    job_id = client.post("/api/analyze", json={"symbol": "AAPL"}).json()["job_id"]
    _poll(job_id)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409


def test_concurrent_submit_is_rejected_409_and_handler_is_nonblocking():
    _FakeApp.gate = threading.Event()
    first = client.post("/api/analyze", json={"symbol": "NVDA"})  # returns immediately
    assert first.status_code == 202
    # Worker is blocked in analyze_stock → job is active; a 2nd submit is 409.
    second = client.post("/api/analyze", json={"symbol": "AMD"})
    assert second.status_code == 409
    # Status endpoint stays responsive while the run blocks.
    running = client.get(f"/api/jobs/{first.json()['job_id']}").json()
    assert running["state"] in ("queued", "running")
    _FakeApp.gate.set()  # release the worker
    done = _poll(first.json()["job_id"])
    assert done["state"] == "completed"
