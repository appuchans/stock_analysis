"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _clear_tool_caches():
    """The tool caches (memory + disk) must not leak results between tests."""
    from src.stock_analysis.tools import cache

    def _wipe():
        cache._memory_cache.clear()
        d = cache._disk_path("")  # resolves/creates the dir; returns ".json" leaf
        if d:
            import glob
            import os
            for f in glob.glob(os.path.join(os.path.dirname(d), "*.json")):
                try:
                    os.remove(f)
                except OSError:
                    pass

    _wipe()
    yield
    _wipe()


@pytest.fixture(autouse=True)
def _reset_llm_budget():
    """Budget state must not leak between tests."""
    from src.stock_analysis import llm_budget

    llm_budget.reset()
    yield
    llm_budget.reset()
