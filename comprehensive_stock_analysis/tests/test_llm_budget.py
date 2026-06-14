"""Tests for the hard LLM-call budget — runaway loops must be impossible."""

from unittest.mock import patch

import pytest

from src.stock_analysis import llm_budget
from src.stock_analysis.llm_budget import LLMBudgetExceededError


class TestBudgetCounter:
    def test_raises_beyond_limit(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        monkeypatch.setattr(settings, "max_llm_calls_per_run", 5)
        llm_budget.reset()
        for _ in range(5):
            llm_budget.check_and_increment()
        with pytest.raises(LLMBudgetExceededError, match="budget exhausted"):
            llm_budget.check_and_increment()
        # And it keeps refusing — no recovery within the run
        with pytest.raises(LLMBudgetExceededError):
            llm_budget.check_and_increment()

    def test_reset_starts_new_window(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        monkeypatch.setattr(settings, "max_llm_calls_per_run", 2)
        llm_budget.reset()
        llm_budget.check_and_increment()
        llm_budget.check_and_increment()
        with pytest.raises(LLMBudgetExceededError):
            llm_budget.check_and_increment()
        llm_budget.reset()
        llm_budget.check_and_increment()  # fresh window

    def test_batch_multiplier_scales_allowance(self, monkeypatch):
        from src.stock_analysis.config.settings import settings
        monkeypatch.setattr(settings, "max_llm_calls_per_run", 2)
        llm_budget.reset(allowance_multiplier=3)
        for _ in range(6):
            llm_budget.check_and_increment()
        with pytest.raises(LLMBudgetExceededError):
            llm_budget.check_and_increment()


class TestBudgetedLLM:
    def test_no_request_reaches_provider_past_budget(self, monkeypatch):
        """The guarantee: past the cap, the provider call is never invoked."""
        from src.stock_analysis.config.settings import settings
        from src.stock_analysis.agents.base_agent import _with_budget

        monkeypatch.setattr(settings, "max_llm_calls_per_run", 3)
        llm_budget.reset()

        provider_calls = {"n": 0}

        class _FakeLLM:
            def call(self, *a, **k):
                provider_calls["n"] += 1
                return "ok"

        llm = _with_budget(_FakeLLM())
        for _ in range(3):
            assert llm.call("hi") == "ok"
        for _ in range(10):  # a runaway loop hammering the LLM
            with pytest.raises(LLMBudgetExceededError):
                llm.call("hi")
        assert provider_calls["n"] == 3  # not one request beyond the budget

    def test_every_agent_gets_budgeted_llm(self):
        """Real agent LLMs (native provider instances) carry the budget wrapper."""
        from src.stock_analysis.agents.base_agent import BaseAgent

        agent = BaseAgent("fundamental_analyst")
        llm = agent._build_llm()
        assert llm.call.__name__ == "_budgeted_call"
        if hasattr(llm, "acall"):
            assert llm.acall.__name__ == "_budgeted_acall"
