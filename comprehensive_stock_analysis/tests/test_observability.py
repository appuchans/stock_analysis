"""Tests for the token meter, credential preflight, and shared HTTP session."""

from types import SimpleNamespace

from src.stock_analysis import token_meter
from src.stock_analysis.agents.base_agent import preflight_llm_credentials
from src.stock_analysis.config import settings as settings_mod
from src.stock_analysis.tools import _http


# ── token_meter ────────────────────────────────────────────────────────────────

def _usage(total, prompt, completion, requests=1, cached=0):
    return SimpleNamespace(
        total_tokens=total, prompt_tokens=prompt, completion_tokens=completion,
        cached_prompt_tokens=cached, successful_requests=requests,
    )


def test_token_meter_accumulates_across_crews():
    token_meter.reset()
    token_meter.add(_usage(100, 70, 30))
    token_meter.add(_usage(50, 40, 10, requests=2))
    snap = token_meter.snapshot()
    assert snap["total_tokens"] == 150
    assert snap["prompt_tokens"] == 110
    assert snap["completion_tokens"] == 40
    assert snap["successful_requests"] == 3


def test_token_meter_ignores_none():
    token_meter.reset()
    token_meter.add(None)
    assert token_meter.snapshot()["total_tokens"] == 0


def test_token_meter_reset_clears():
    token_meter.add(_usage(100, 70, 30))
    token_meter.reset()
    assert token_meter.snapshot()["total_tokens"] == 0


def test_token_alert_fires_over_threshold(monkeypatch, caplog):
    monkeypatch.setattr(settings_mod.settings, "llm_token_alert", 100)
    token_meter.reset()
    token_meter.add(_usage(250, 200, 50))
    with caplog.at_level("WARNING"):
        token_meter.check_alert()
    assert any("token-alert" in r.message for r in caplog.records)


def test_token_alert_silent_when_disabled(monkeypatch, caplog):
    monkeypatch.setattr(settings_mod.settings, "llm_token_alert", 0)
    token_meter.reset()
    token_meter.add(_usage(10_000, 9000, 1000))
    with caplog.at_level("WARNING"):
        token_meter.check_alert()
    assert not any("token-alert" in r.message for r in caplog.records)


# ── credential preflight ───────────────────────────────────────────────────────

def test_preflight_flags_missing_openai_key(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "openai_api_key", None)
    problems = preflight_llm_credentials(provider_override="openai")
    assert problems and "OPENAI_API_KEY" in problems[0]


def test_preflight_ok_when_key_present(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "openai_api_key", "sk-test")
    assert preflight_llm_credentials(provider_override="openai") == []


def test_preflight_ollama_needs_no_key(monkeypatch):
    monkeypatch.setattr(settings_mod.settings, "openai_api_key", None)
    monkeypatch.setattr(settings_mod.settings, "anthropic_api_key", None)
    assert preflight_llm_credentials(provider_override="ollama") == []


# ── shared HTTP session ────────────────────────────────────────────────────────

def test_http_session_has_retry_adapter():
    adapter = _http.SESSION.get_adapter("https://example.com")
    assert adapter.max_retries.total == 2
    assert 429 in adapter.max_retries.status_forcelist


def test_http_get_applies_default_timeout(monkeypatch):
    captured = {}

    def _fake(url, **kwargs):
        captured.update(kwargs)
        return "resp"

    monkeypatch.setattr(_http.SESSION, "get", _fake)
    _http.get("https://example.com")
    assert captured["timeout"] == _http.DEFAULT_TIMEOUT
