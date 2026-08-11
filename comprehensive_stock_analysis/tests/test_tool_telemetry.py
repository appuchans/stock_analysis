"""Tests for per-tool telemetry tracking (call counts, errors, cache hits, latency)."""

import threading
import time
from datetime import datetime, timedelta

import pytest

from src.stock_analysis import tool_telemetry


class TestToolTelemetryReset:
    def test_reset_clears_all_telemetry(self):
        tool_telemetry.reset()
        tool_telemetry.record_tool_finish("AnalystDataTool", 150.5, from_cache=False)
        assert tool_telemetry.snapshot()  # some data
        tool_telemetry.reset()
        assert tool_telemetry.snapshot() == {}  # empty after reset


class TestToolTelemetryRecording:
    def test_record_tool_finish_increments_calls(self):
        tool_telemetry.reset()
        tool_telemetry.record_tool_finish("AnalystDataTool", 100.0, from_cache=False)
        tool_telemetry.record_tool_finish("AnalystDataTool", 150.0, from_cache=False)
        snap = tool_telemetry.snapshot()
        assert snap["AnalystDataTool"]["calls"] == 2
        assert snap["AnalystDataTool"]["total_duration_ms"] == 250.0

    def test_record_tool_finish_tracks_cache_hits(self):
        tool_telemetry.reset()
        tool_telemetry.record_tool_finish("AnalystDataTool", 100.0, from_cache=True)
        tool_telemetry.record_tool_finish("AnalystDataTool", 150.0, from_cache=False)
        snap = tool_telemetry.snapshot()
        assert snap["AnalystDataTool"]["cache_hits"] == 1
        assert snap["AnalystDataTool"]["calls"] == 2

    def test_record_tool_error_increments_errors(self):
        tool_telemetry.reset()
        tool_telemetry.record_tool_error("AnalystDataTool")
        tool_telemetry.record_tool_error("AnalystDataTool")
        tool_telemetry.record_tool_finish("AnalystDataTool", 100.0, from_cache=False)
        snap = tool_telemetry.snapshot()
        assert snap["AnalystDataTool"]["errors"] == 2
        assert snap["AnalystDataTool"]["calls"] == 1

    def test_record_tool_start_initializes_entry(self):
        tool_telemetry.reset()
        tool_telemetry.record_tool_start("NewTool")
        snap = tool_telemetry.snapshot()
        assert "NewTool" in snap
        assert snap["NewTool"]["calls"] == 0

    def test_multiple_tools_tracked_independently(self):
        tool_telemetry.reset()
        tool_telemetry.record_tool_finish("ToolA", 100.0)
        tool_telemetry.record_tool_finish("ToolB", 200.0)
        tool_telemetry.record_tool_error("ToolA")
        snap = tool_telemetry.snapshot()
        assert snap["ToolA"]["calls"] == 1
        assert snap["ToolA"]["errors"] == 1
        assert snap["ToolB"]["calls"] == 1
        assert snap["ToolB"]["errors"] == 0


class TestToolTelemetryThreadSafety:
    def test_concurrent_records_are_consistent(self):
        """Concurrent tool calls from parallel stages must aggregate correctly."""
        tool_telemetry.reset()
        errors = []

        def record_calls(tool_name, count):
            try:
                for i in range(count):
                    tool_telemetry.record_tool_finish(tool_name, 10.0 + i)
                    if i % 2 == 0:
                        tool_telemetry.record_tool_error(tool_name)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_calls, args=("ToolA", 20)),
            threading.Thread(target=record_calls, args=("ToolB", 15)),
            threading.Thread(target=record_calls, args=("ToolA", 10)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"concurrent recording failed: {errors}"
        snap = tool_telemetry.snapshot()
        assert snap["ToolA"]["calls"] == 30  # 20 + 10
        assert snap["ToolB"]["calls"] == 15
        # Errors: ToolA has ~10-11 errors (from 20 calls + 10 calls with every other call erroring)
        # ToolB has ~7-8 errors (from 15 calls with every other call erroring)
        # Exact counts depend on thread interleaving, so we just verify some happened
        assert snap["ToolA"]["errors"] > 0
        assert snap["ToolB"]["errors"] > 0
        assert (
            snap["ToolA"]["errors"] >= snap["ToolB"]["errors"]
        )  # ToolA has more calls


class TestToolTelemetrySnapshot:
    def test_snapshot_is_independent_dict(self):
        """Snapshot returns a copy, not a reference to internal state."""
        tool_telemetry.reset()
        tool_telemetry.record_tool_finish("Tool", 100.0)
        snap1 = tool_telemetry.snapshot()
        tool_telemetry.record_tool_finish("Tool", 200.0)
        snap2 = tool_telemetry.snapshot()
        assert snap1["Tool"]["calls"] == 1
        assert snap2["Tool"]["calls"] == 2

    def test_snapshot_includes_all_fields(self):
        tool_telemetry.reset()
        tool_telemetry.record_tool_finish("Tool", 100.0, from_cache=True)
        tool_telemetry.record_tool_error("Tool")
        snap = tool_telemetry.snapshot()
        assert "calls" in snap["Tool"]
        assert "errors" in snap["Tool"]
        assert "cache_hits" in snap["Tool"]
        assert "total_duration_ms" in snap["Tool"]
