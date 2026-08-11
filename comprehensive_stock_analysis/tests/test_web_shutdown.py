"""Shutdown-during-analysis handling.

Regression cover for the 2026-08-11 incident: the server went down mid-run and
every stage failed with ``cannot schedule new futures after shutdown`` (Python's
process-global executor flag), leaving the job recorded as ``failed`` with an
error that said nothing about the real cause.
"""

import logging

import pytest

from stock_analysis.web.jobs import (
    _SHUTDOWN_MESSAGE,
    Job,
    JobManager,
    _is_shutdown_error,
)


class TestShutdownErrorDetection:
    def test_matches_the_cpython_message(self):
        assert _is_shutdown_error("cannot schedule new futures after shutdown")

    def test_matches_when_wrapped_in_other_text(self):
        assert _is_shutdown_error(
            "OpenAI API call failed: cannot schedule new futures after shutdown"
        )

    @pytest.mark.parametrize("value", [None, "", "rate limit exceeded"])
    def test_ignores_unrelated_errors(self, value):
        assert not _is_shutdown_error(value)


class TestRunClassification:
    """A shutdown-induced failure must read as ``aborted``, not ``failed`` —
    via the message alone, so a hard kill that bypasses shutdown() is covered."""

    def _job(self):
        return Job(
            id="j1", symbol="MSFT", depth="standard", asset_type="auto", use_cache=True
        )

    def test_result_path_is_reclassified(self, monkeypatch, tmp_path):
        mgr = JobManager()
        job = self._job()
        mgr._jobs[job.id] = job

        class _App:
            def __init__(self, **kw):
                pass

            def analyze_stock(self, symbol):
                return {
                    "status": "failed",
                    "error": "cannot schedule new futures after shutdown",
                }

        monkeypatch.setattr("stock_analysis.main.StockAnalysisApp", _App)
        monkeypatch.setattr(
            "stock_analysis.tools.free_data_collection.resolve_symbol",
            lambda s: {"name": "Microsoft Corporation"},
        )
        mgr._run(job)

        assert job.state == "aborted"
        assert job.stage == "Aborted"
        assert job.error == _SHUTDOWN_MESSAGE

    def test_exception_path_is_reclassified(self, monkeypatch):
        mgr = JobManager()
        job = self._job()
        mgr._jobs[job.id] = job

        class _App:
            def __init__(self, **kw):
                pass

            def analyze_stock(self, symbol):
                raise RuntimeError("cannot schedule new futures after shutdown")

        monkeypatch.setattr("stock_analysis.main.StockAnalysisApp", _App)
        monkeypatch.setattr(
            "stock_analysis.tools.free_data_collection.resolve_symbol",
            lambda s: {"name": "Microsoft Corporation"},
        )
        mgr._run(job)

        assert job.state == "aborted"
        assert job.error == _SHUTDOWN_MESSAGE

    def test_a_genuine_failure_still_fails(self, monkeypatch):
        """The reclassification must not swallow real errors."""
        mgr = JobManager()
        job = self._job()
        mgr._jobs[job.id] = job

        class _App:
            def __init__(self, **kw):
                pass

            def analyze_stock(self, symbol):
                return {"status": "failed", "error": "provider returned 500"}

        monkeypatch.setattr("stock_analysis.main.StockAnalysisApp", _App)
        monkeypatch.setattr(
            "stock_analysis.tools.free_data_collection.resolve_symbol",
            lambda s: {"name": "Microsoft Corporation"},
        )
        mgr._run(job)

        assert job.state == "failed"
        assert job.error == "provider returned 500"


class TestManagerShutdown:
    def test_aborts_the_active_job(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "stock_analysis.llm_budget.request_abort", lambda: called.append(True)
        )
        mgr = JobManager()
        job = Job(
            id="j1", symbol="MSFT", depth="standard", asset_type="auto", use_cache=True
        )
        job.state = "running"
        mgr._jobs[job.id] = job
        mgr._active_id = job.id

        mgr.shutdown()

        assert job.cancel_requested is True
        assert called == [True], "llm_budget abort must be requested"

    def test_leaves_queued_jobs_for_recovery(self, monkeypatch):
        """Queued jobs must stay ``queued`` so recover() re-queues them next
        start, rather than being marked failed on the way out."""
        monkeypatch.setattr("stock_analysis.llm_budget.request_abort", lambda: None)
        mgr = JobManager()
        queued = Job(
            id="j2", symbol="AAPL", depth="quick", asset_type="auto", use_cache=True
        )
        mgr._jobs[queued.id] = queued
        mgr._pending.append(queued.id)

        mgr.shutdown()

        assert queued.state == "queued"
        assert queued.cancel_requested is False

    def test_is_idempotent(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "stock_analysis.llm_budget.request_abort", lambda: calls.append(1)
        )
        mgr = JobManager()
        job = Job(
            id="j1", symbol="MSFT", depth="standard", asset_type="auto", use_cache=True
        )
        job.state = "running"
        mgr._jobs[job.id] = job
        mgr._active_id = job.id

        mgr.shutdown()
        mgr.shutdown()

        assert len(calls) == 1, "a second shutdown must be a no-op"

    def test_no_active_job_is_safe(self, monkeypatch):
        monkeypatch.setattr("stock_analysis.llm_budget.request_abort", lambda: None)
        JobManager().shutdown()  # must not raise


class TestDiagnostics:
    def test_install_is_idempotent(self, tmp_path, monkeypatch):
        """Guard the re-entry flag without letting the real installers touch
        this process — they replace sys.excepthook and signal handlers, which
        would leak into every later test."""
        from stock_analysis import diagnostics

        calls = []
        monkeypatch.setattr(
            diagnostics, "_install_faulthandler", lambda p: calls.append("fault")
        )
        monkeypatch.setattr(
            diagnostics, "_install_excepthooks", lambda: calls.append("hooks")
        )
        monkeypatch.setattr(
            diagnostics, "_install_signal_logging", lambda: calls.append("signals")
        )
        monkeypatch.setattr(
            diagnostics, "_install_exit_logging", lambda role: calls.append("exit")
        )
        monkeypatch.setattr(diagnostics, "_installed", False)

        diagnostics.install(tmp_path / "crew.log", role="test")
        diagnostics.install(tmp_path / "crew.log", role="test")

        assert calls == [
            "fault",
            "hooks",
            "signals",
            "exit",
        ], "the second install must be a no-op"

    def test_fault_log_sits_beside_the_main_log(self, tmp_path):
        from stock_analysis import diagnostics

        p = diagnostics._fault_log_path(tmp_path / "crew_output.log")
        assert p.name == "crew_output_faults.log"
        assert p.parent == tmp_path

    def test_attach_uvicorn_logging_enables_propagation(self):
        from stock_analysis import diagnostics

        logging.getLogger("uvicorn.error").propagate = False
        diagnostics.attach_uvicorn_logging()
        assert logging.getLogger("uvicorn.error").propagate is True
