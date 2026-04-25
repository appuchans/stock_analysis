"""Application settings and configuration management."""

from typing import Any, List, Optional

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    LLM settings here act as global overrides on top of llm_config.yaml defaults.
    Leave them as empty strings to rely solely on llm_config.yaml.
    """

    # ── API Keys ──────────────────────────────────────────────────────────────
    openai_api_key: Optional[str] = Field(None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(None, validation_alias="ANTHROPIC_API_KEY")
    fred_api_key: str = Field("demo", validation_alias="FRED_API_KEY")

    # ── Application ───────────────────────────────────────────────────────────
    debug: bool = Field(False, validation_alias="DEBUG")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    max_workers: int = Field(4, validation_alias="MAX_WORKERS")
    cache_ttl: int = Field(3600, validation_alias="CACHE_TTL")

    # ── LLM — global overrides (empty string = defer to llm_config.yaml) ─────
    # Set these to switch all agents at once without editing llm_config.yaml.
    llm_provider: str = Field("", validation_alias="LLM_PROVIDER")
    llm_model: str = Field("", validation_alias="LLM_MODEL")
    temperature: float = Field(0.1, validation_alias="LLM_TEMPERATURE")
    max_tokens: int = Field(4000, validation_alias="LLM_MAX_TOKENS")

    # ── Embedder — for Crew-level memory ──────────────────────────────────────
    # Empty string = defer to llm_config.yaml embedder section.
    embedder_provider: str = Field("", validation_alias="EMBEDDER_PROVIDER")
    embedder_model: str = Field("", validation_alias="EMBEDDER_MODEL")

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        "sqlite:///./stock_analysis.db", validation_alias="DATABASE_URL"
    )
    redis_url: str = Field("redis://localhost:6379/0", validation_alias="REDIS_URL")

    # ── Data Sources ──────────────────────────────────────────────────────────
    yahoo_finance_enabled: bool = Field(True, validation_alias="YAHOO_FINANCE_ENABLED")
    sec_edgar_enabled: bool = Field(True, validation_alias="SEC_EDGAR_ENABLED")
    fred_enabled: bool = Field(True, validation_alias="FRED_ENABLED")
    rss_feeds_enabled: bool = Field(True, validation_alias="RSS_FEEDS_ENABLED")
    web_scraping_enabled: bool = Field(True, validation_alias="WEB_SCRAPING_ENABLED")

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_per_minute: int = Field(60, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(1000, validation_alias="RATE_LIMIT_PER_HOUR")

    # ── Reports ───────────────────────────────────────────────────────────────
    report_format: str = Field("json", validation_alias="REPORT_FORMAT")
    report_template: str = Field("default", validation_alias="REPORT_TEMPLATE")
    report_output_dir: str = Field("./reports", validation_alias="REPORT_OUTPUT_DIR")

    # ── Notifications ─────────────────────────────────────────────────────────
    email_enabled: bool = Field(False, validation_alias="EMAIL_ENABLED")
    email_smtp_server: str = Field("smtp.gmail.com", validation_alias="EMAIL_SMTP_SERVER")
    email_smtp_port: int = Field(587, validation_alias="EMAIL_SMTP_PORT")
    email_username: Optional[str] = Field(None, validation_alias="EMAIL_USERNAME")
    email_password: Optional[str] = Field(None, validation_alias="EMAIL_PASSWORD")
    email_from: Optional[str] = Field(None, validation_alias="EMAIL_FROM")

    # ── Webhooks ──────────────────────────────────────────────────────────────
    webhook_enabled: bool = Field(False, validation_alias="WEBHOOK_ENABLED")
    webhook_url: Optional[str] = Field(None, validation_alias="WEBHOOK_URL")
    webhook_secret: Optional[str] = Field(None, validation_alias="WEBHOOK_SECRET")

    # ── Security ──────────────────────────────────────────────────────────────
    secret_key: str = Field(
        "your-secret-key-change-in-production", validation_alias="SECRET_KEY"
    )
    jwt_secret_key: str = Field(
        "your-jwt-secret-key-change-in-production", validation_alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field("HS256", validation_alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        30, validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    # ── Monitoring ────────────────────────────────────────────────────────────
    sentry_dsn: Optional[str] = Field(None, validation_alias="SENTRY_DSN")
    prometheus_enabled: bool = Field(False, validation_alias="PROMETHEUS_ENABLED")
    prometheus_port: int = Field(8000, validation_alias="PROMETHEUS_PORT")

    # ── Analysis ──────────────────────────────────────────────────────────────
    analysis_timeframe: str = Field("1y", validation_alias="ANALYSIS_TIMEFRAME")
    technical_indicators: List[str] = Field(
        default=["SMA", "EMA", "RSI", "MACD", "BB", "STOCH", "ADX", "CCI", "WILLR", "MOM"],
        validation_alias="TECHNICAL_INDICATORS",
    )
    fundamental_metrics: List[str] = Field(
        default=[
            "PE", "PB", "PS", "PEG", "EV_EBITDA", "ROE", "ROA",
            "ROIC", "DEBT_EQUITY", "CURRENT_RATIO",
        ],
        validation_alias="FUNDAMENTAL_METRICS",
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        placeholder = "your-secret-key-change-in-production"
        if v == placeholder and not (info.data or {}).get("debug", True):
            raise ValueError(
                "SECRET_KEY must be changed from the default placeholder in production. "
                "Set SECRET_KEY or enable DEBUG=true."
            )
        return v

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, v: str, info: ValidationInfo) -> str:
        placeholder = "your-jwt-secret-key-change-in-production"
        if v == placeholder and not (info.data or {}).get("debug", True):
            raise ValueError(
                "JWT_SECRET_KEY must be changed from the default placeholder in production. "
                "Set JWT_SECRET_KEY or enable DEBUG=true."
            )
        return v

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
        if not v:
            return v  # empty = defer to llm_config.yaml
        valid = {
            "openai", "anthropic", "ollama", "azure",
            "groq", "mistral", "cohere", "bedrock",
            "huggingface", "vertexai",
        }
        if v.lower() not in valid:
            raise ValueError(
                f"LLM_PROVIDER must be one of {sorted(valid)} (got '{v}'). "
                "Add custom providers to config/llm_config.yaml provider_prefixes."
            )
        return v.lower()

    @field_validator("report_format")
    @classmethod
    def validate_report_format(cls, v: str) -> str:
        valid = {"pdf", "html", "json", "csv", "xlsx"}
        if v.lower() not in valid:
            raise ValueError(f"REPORT_FORMAT must be one of {sorted(valid)}")
        return v.lower()

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "populate_by_name": True,
    }


# Global settings instance
settings = Settings()
