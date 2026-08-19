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


@pytest.fixture(autouse=True)
def _no_premium_provider_keys(monkeypatch):
    """Premium providers stay unconfigured unless a test opts in.

    Provider keys are read from the developer's .env, so a machine with real
    credentials ran a different test suite from CI's: adding Alpaca to the
    price chain made four router tests reach the live API and assert against
    whichever provider happened to answer. Tests that want a provider construct
    it directly or set the key themselves.
    """
    from src.stock_analysis.config.settings import settings

    for field in (
        "fmp_api_key",
        "polygon_api_key",
        "alpaca_api_key",
        "alpaca_api_secret",
        "sec_api_key",
        "finnhub_api_key",
        "alpha_vantage_api_key",
        "marketaux_api_key",
    ):
        if hasattr(settings, field):
            monkeypatch.setattr(settings, field, None, raising=False)
    yield
