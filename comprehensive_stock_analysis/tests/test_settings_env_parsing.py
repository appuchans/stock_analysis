"""Tests for Settings env-var parsing edge cases.

An empty env var (``LLM_TEMPERATURE=`` in .env, or an exported-but-empty shell
variable) used to crash Settings() at import time with a ValidationError —
killing every entry point before printing anything useful. Empty values must
behave exactly like unset ones.
"""


class TestEmptyEnvVars:
    def test_empty_numeric_env_vars_do_not_crash(self, monkeypatch):
        """Every numeric field tolerates a present-but-empty env var."""
        from src.stock_analysis.config.settings import Settings

        for var in (
            "LLM_TEMPERATURE",
            "LLM_MAX_TOKENS",
            "MAX_WORKERS",
            "CACHE_TTL",
            "DATA_CACHE_TTL",
            "MAX_LLM_CALLS_PER_RUN",
            "LLM_TOKEN_ALERT",
            "WEB_PORT",
            "ALERT_SMTP_PORT",
        ):
            monkeypatch.setenv(var, "")

        s = Settings(_env_file=None)
        # Optional numeric field → None (defer to llm_config.yaml)
        assert s.temperature is None
        # Non-optional fields keep their defaults
        assert s.max_tokens == 4000
        assert s.web_port == 8000
        assert s.max_llm_calls_per_run == 300

    def test_set_value_still_wins_over_default(self, monkeypatch):
        from src.stock_analysis.config.settings import Settings

        monkeypatch.setenv("WEB_PORT", "9000")
        assert Settings(_env_file=None).web_port == 9000

    def test_empty_string_fields_unchanged(self, monkeypatch):
        """String fields already treat '' as 'defer' — that contract holds."""
        from src.stock_analysis.config.settings import Settings

        monkeypatch.setenv("LLM_PROVIDER", "")
        assert Settings(_env_file=None).llm_provider == ""
