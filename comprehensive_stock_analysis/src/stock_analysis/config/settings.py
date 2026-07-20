"""Application settings and configuration management."""

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Project root for anchoring output paths, so reports/logs/data land in the
# project directory no matter which directory the app is launched from.
# settings.py lives at <root>/src/stock_analysis/config/settings.py; for
# non-src installs (e.g. a wheel) fall back to the current working directory.
_pkg_parent = Path(__file__).resolve().parents[2]
PROJECT_ROOT = _pkg_parent.parent if _pkg_parent.name == "src" else Path.cwd()


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    LLM settings here act as global overrides on top of llm_config.yaml defaults.
    Leave them as empty strings to rely solely on llm_config.yaml.
    """

    # ── API Keys ──────────────────────────────────────────────────────────────
    openai_api_key: Optional[str] = Field(None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(None, validation_alias="ANTHROPIC_API_KEY")
    fred_api_key: str = Field("demo", validation_alias="FRED_API_KEY")
    # Required by SEC EDGAR terms of service — set to a real contact email.
    # A warning is logged at startup if the placeholder default is still in use.
    sec_edgar_email: str = Field("contact@example.com", validation_alias="SEC_EDGAR_EMAIL")

    # ── Application ───────────────────────────────────────────────────────────
    debug: bool = Field(False, validation_alias="DEBUG")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    max_workers: int = Field(4, validation_alias="MAX_WORKERS")
    cache_ttl: int = Field(3600, validation_alias="CACHE_TTL")
    # Reuse the full structured data fetch for the same symbol within this
    # window (cross-process, disk-backed). Default 24h — a re-run of the same
    # ticker that day skips all data collection. Set to 0 to always re-fetch.
    data_cache_ttl: int = Field(86400, validation_alias="DATA_CACHE_TTL")
    # Hard per-run LLM-call cap — safety stop against runaway agent loops.
    # ~2x a worst-case legitimate deep run; a normal standard run uses <60.
    max_llm_calls_per_run: int = Field(300, validation_alias="MAX_LLM_CALLS_PER_RUN")
    # Soft quota alert — log a WARNING when a run's total tokens exceed this.
    # 0 disables. Provider-agnostic (tokens, not a hard-coded price table).
    llm_token_alert: int = Field(0, validation_alias="LLM_TOKEN_ALERT")
    # Local web UI (single-user). Defaults to localhost-only, no auth.
    web_host: str = Field("127.0.0.1", validation_alias="WEB_HOST")
    web_port: int = Field(8000, validation_alias="WEB_PORT")

    # ── Alerts ────────────────────────────────────────────────────────────────
    alert_email: str = Field("", validation_alias="ALERT_EMAIL")
    alert_smtp_host: str = Field("smtp.gmail.com", validation_alias="ALERT_SMTP_HOST")
    alert_smtp_port: int = Field(587, validation_alias="ALERT_SMTP_PORT")
    alert_smtp_user: str = Field("", validation_alias="ALERT_SMTP_USER")
    alert_smtp_password: str = Field("", validation_alias="ALERT_SMTP_PASSWORD")
    alert_webhook_url: str = Field("", validation_alias="ALERT_WEBHOOK_URL")

    # ── LLM — global overrides (empty string = defer to llm_config.yaml) ─────
    # Set these to switch all agents at once without editing llm_config.yaml.
    llm_provider: str = Field("", validation_alias="LLM_PROVIDER")
    llm_model: str = Field("", validation_alias="LLM_MODEL")
    temperature: float = Field(0.1, validation_alias="LLM_TEMPERATURE")
    max_tokens: int = Field(4000, validation_alias="LLM_MAX_TOKENS")

    # ── Crew output log ───────────────────────────────────────────────────────
    crew_log_file: str = Field(
        str(PROJECT_ROOT / "logs" / "crew_output.log"), validation_alias="CREW_LOG_FILE"
    )

    # ── Cache backend (optional — degrades to no-cache without Redis) ─────────
    redis_url: str = Field("redis://localhost:6379/0", validation_alias="REDIS_URL")

    # ── Data source toggles ───────────────────────────────────────────────────
    sec_edgar_enabled: bool = Field(True, validation_alias="SEC_EDGAR_ENABLED")
    fred_enabled: bool = Field(True, validation_alias="FRED_ENABLED")
    rss_feeds_enabled: bool = Field(True, validation_alias="RSS_FEEDS_ENABLED")
    web_scraping_enabled: bool = Field(True, validation_alias="WEB_SCRAPING_ENABLED")

    # ── Output locations (relative values anchor to the project root) ─────────
    report_output_dir: str = Field(
        str(PROJECT_ROOT / "reports"), validation_alias="REPORT_OUTPUT_DIR"
    )
    data_output_dir: str = Field(
        str(PROJECT_ROOT / "data"), validation_alias="DATA_OUTPUT_DIR"
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("report_output_dir", "data_output_dir", "crew_log_file")
    @classmethod
    def anchor_relative_paths_to_project_root(cls, v: str) -> str:
        """Anchor relative output paths to the project root.

        Output must land in the project directory regardless of the cwd the
        app happens to be launched from (e.g. REPORT_OUTPUT_DIR=./reports in
        .env means <project>/reports, not <cwd>/reports).
        """
        p = Path(v)
        return str(p if p.is_absolute() else (PROJECT_ROOT / p).resolve())

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(valid)}")
        return upper

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """Normalise the provider name — not a whitelist.

        BaseAgent._build_llm resolves any provider via LiteLLM's generic
        "<provider>/<model>" convention (config/llm_config.yaml's
        provider_prefixes just documents known ones; unlisted providers fall
        back to that same convention), so this must not reject providers the
        rest of the system already supports.
        """
        if not v:
            return v  # empty = defer to llm_config.yaml
        return v.strip().lower()

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "populate_by_name": True,
        # Ignore unknown keys so a stale/legacy .env never blocks startup
        "extra": "ignore",
    }


# Global settings instance
settings = Settings()
