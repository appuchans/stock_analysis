"""Tests for LLM temperature resolution across the config layers.

The temperature chain had a class of bug where a hardcoded 0.1 default at any
layer (settings, llm_config.yaml global, Pydantic field defaults) silently
overrode the layers below it and sent an unsupported value to models that only
accept their own default (e.g. gpt-5.6-luna). These tests pin the fixed
semantics: unset means None ("omit from the request"), and an explicit value —
including 0.0 — always wins.
"""

import pytest


@pytest.fixture
def _no_temperature_env(monkeypatch):
    """Ensure no LLM_TEMPERATURE leaks from the developer's environment."""
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)


class TestTemperatureResolution:
    def test_unset_everywhere_resolves_to_none(self, _no_temperature_env):
        """No layer sets a temperature → resolved config must be None.

        None is what makes crewai.LLM omit the param entirely (both the
        generic LiteLLM path and the native OpenAICompletion class strip
        None), letting the model use its own default.
        """
        from src.stock_analysis.agents.base_agent import BaseAgent

        agent = BaseAgent("technical_analyst")
        assert agent.get_resolved_llm_config()["temperature"] is None

    def test_unset_temperature_builds_llm_with_none(self, _no_temperature_env):
        """The built crewai.LLM itself carries temperature=None."""
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
        try:
            from src.stock_analysis.agents.base_agent import BaseAgent

            agent = BaseAgent("technical_analyst")
            assert agent._build_llm().temperature is None
        finally:
            monkeypatch.undo()

    def test_env_zero_is_applied_not_treated_as_unset(self, monkeypatch):
        """LLM_TEMPERATURE=0.0 must survive: 'is not None' checks everywhere,
        never truthiness — 0.0 is a legitimate deterministic-output setting."""
        monkeypatch.setenv("LLM_TEMPERATURE", "0.0")

        # Settings is a singleton instantiated at import; re-read the env var
        # through a fresh instance to avoid reloading the module globally.
        from src.stock_analysis.config.settings import Settings

        assert Settings(_env_file=None).temperature == 0.0

        # Patch the singleton BEFORE constructing the agent — resolution
        # happens in BaseAgent.__init__, not at get_resolved_llm_config().
        monkeypatch.setattr(
            "src.stock_analysis.config.settings.settings.temperature", 0.0
        )

        from src.stock_analysis.agents.base_agent import BaseAgent

        agent = BaseAgent("technical_analyst")
        assert agent.get_resolved_llm_config()["temperature"] == 0.0

    def test_yaml_per_agent_override_wins_over_env(self, monkeypatch):
        """llm_config.yaml per-agent overrides outrank env vars (step 3 > 2)."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
        monkeypatch.setattr(
            "src.stock_analysis.config.settings.settings.temperature", 0.9
        )

        from src.stock_analysis.config.loader import config_loader

        # investment_advisor has per-agent entries in llm_config.yaml; give it
        # a temperature override via the loader's parsed agents dict.
        cfg = config_loader.load_llm_config()
        original = dict(cfg.agents.get("investment_advisor") or {})
        cfg.agents["investment_advisor"] = {**original, "temperature": 0.2}

        try:
            from src.stock_analysis.agents.base_agent import BaseAgent

            agent = BaseAgent("investment_advisor")
            assert agent.get_resolved_llm_config()["temperature"] == 0.2
        finally:
            cfg.agents["investment_advisor"] = original

    def test_reactive_fallback_clears_rejected_temperature(self, monkeypatch):
        """When a provider rejects a set temperature with its 400 message, the
        wrapper retries once with temperature cleared — the safety net that
        stays in place even though the YAML no longer sends 0.1 by default."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")

        from crewai import LLM

        from src.stock_analysis.agents.base_agent import _with_llm_param_fallbacks

        llm = LLM(model="openai/gpt-5.6-luna", temperature=0.1, max_tokens=100)

        calls = []

        def raising_then_ok(*args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise Exception(
                    "Unsupported value: 'temperature' does not support 0.1 "
                    "with this model. Only the default (1) value is supported."
                )
            return "ok"

        llm.call = raising_then_ok
        wrapped = _with_llm_param_fallbacks(llm)
        assert wrapped.call(messages="hi") == "ok"
        assert len(calls) == 2
        assert llm.temperature is None
