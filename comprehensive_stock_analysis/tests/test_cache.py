"""Cross-process cache behaviour: the disk tier must survive a 'new process'.

These tests force Redis to be unavailable so the memory→disk fallback path is
exercised. The autouse fixture in conftest wipes both tiers between tests.
"""

import pytest

from src.stock_analysis.tools import cache


@pytest.fixture(autouse=True)
def _force_no_redis(monkeypatch):
    """Pin the cache to its no-Redis fallback so disk persistence is tested."""
    monkeypatch.setattr(cache, "_get_redis", lambda: None)


def _simulate_new_process():
    """Clear only the in-process memory tier — the disk tier must remain."""
    cache._memory_cache.clear()


def test_set_then_get_roundtrips_via_disk():
    cache.set_cached("structured", "AAPL", {"price": 100, "blocks": ["a", "b"]}, ttl=3600)
    _simulate_new_process()
    got = cache.get_cached("structured", "AAPL")
    assert got == {"price": 100, "blocks": ["a", "b"]}


def test_miss_returns_none():
    assert cache.get_cached("structured", "ZZZZ") is None


def test_error_dicts_are_not_cached():
    cache.set_cached("structured", "BAD", {"error": "boom"}, ttl=3600)
    _simulate_new_process()
    assert cache.get_cached("structured", "BAD") is None


def test_expired_entry_is_a_miss():
    cache.set_cached("structured", "OLD", {"x": 1}, ttl=0)
    _simulate_new_process()
    assert cache.get_cached("structured", "OLD") is None


def test_namespaces_are_isolated():
    cache.set_cached("structured", "AAPL", {"v": 1}, ttl=3600)
    cache.set_cached("other", "AAPL", {"v": 2}, ttl=3600)
    _simulate_new_process()
    assert cache.get_cached("structured", "AAPL") == {"v": 1}
    assert cache.get_cached("other", "AAPL") == {"v": 2}


def test_flow_no_cache_flag_bypasses_read_but_still_writes():
    """use_data_cache=False must ignore a cached bundle yet refresh the store."""
    from src.stock_analysis.crew.flow_crew import StockAnalysisFlow

    cache.set_cached("structured", "AAPL", {"structured": {"stale": True}}, ttl=3600)

    flow = StockAnalysisFlow(use_data_cache=False)
    flow.state.symbol = "AAPL"
    fresh = {"structured": {"fresh": True}, "technical_summary": None}
    flow._fetch_structured_uncached = lambda: fresh  # type: ignore[method-assign]

    flow._fetch_structured()

    # Read was bypassed — the stale cache was not applied to state…
    assert flow.state.data["structured"] == {"fresh": True}
    # …but the fresh pull refreshed the store for later (normal) runs.
    _simulate_new_process()
    assert cache.get_cached("structured", "AAPL") == fresh


def test_disk_sweep_removes_aged_files(monkeypatch, tmp_path):
    """The one-time sweep deletes cache files older than the age cap."""
    import os
    import time

    d = tmp_path / ".tool_cache"
    d.mkdir()
    fresh = d / "fresh.json"
    stale = d / "stale.json"
    fresh.write_text("{}")
    stale.write_text("{}")
    old = time.time() - (cache._DISK_SWEEP_MAX_AGE + 100)
    os.utime(stale, (old, old))

    cache._sweep_disk_cache(str(d))

    assert fresh.exists()
    assert not stale.exists()


def test_cached_tool_decorator_survives_new_process():
    """A @cached_tool result must be served from disk after memory is cleared."""
    calls = {"n": 0}

    class _Tool:
        name = "Demo Tool"

        @cache.cached_tool(ttl=3600)
        def _run(self, symbol):
            calls["n"] += 1
            return {"symbol": symbol, "value": 42}

    t = _Tool()
    assert t._run("AAPL")["value"] == 42
    assert calls["n"] == 1
    _simulate_new_process()
    assert t._run("AAPL")["value"] == 42
    assert calls["n"] == 1  # served from disk, function not re-invoked
