"""Application settings and configuration management."""

import os
from typing import Optional, List
from pydantic import BaseSettings, Field, validator
from pydantic_settings import BaseSettings as PydanticBaseSettings


class Settings(PydanticBaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys (Only free APIs)
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(None, env="ANTHROPIC_API_KEY")
    fred_api_key: Optional[str] = Field("demo", env="FRED_API_KEY")  # Free with demo key
    
    # Database Configuration
    database_url: str = Field("sqlite:///./stock_analysis.db", env="DATABASE_URL")
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    
    # Application Configuration
    debug: bool = Field(False, env="DEBUG")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    max_workers: int = Field(4, env="MAX_WORKERS")
    cache_ttl: int = Field(3600, env="CACHE_TTL")
    
    # Data Sources Configuration (Only free sources)
    yahoo_finance_enabled: bool = Field(True, env="YAHOO_FINANCE_ENABLED")
    sec_edgar_enabled: bool = Field(True, env="SEC_EDGAR_ENABLED")
    fred_enabled: bool = Field(True, env="FRED_ENABLED")
    rss_feeds_enabled: bool = Field(True, env="RSS_FEEDS_ENABLED")
    web_scraping_enabled: bool = Field(True, env="WEB_SCRAPING_ENABLED")
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(60, env="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(1000, env="RATE_LIMIT_PER_HOUR")
    
    # Report Configuration
    report_format: str = Field("pdf", env="REPORT_FORMAT")
    report_template: str = Field("default", env="REPORT_TEMPLATE")
    report_output_dir: str = Field("./reports", env="REPORT_OUTPUT_DIR")
    
    # Notification Configuration
    email_enabled: bool = Field(False, env="EMAIL_ENABLED")
    email_smtp_server: str = Field("smtp.gmail.com", env="EMAIL_SMTP_SERVER")
    email_smtp_port: int = Field(587, env="EMAIL_SMTP_PORT")
    email_username: Optional[str] = Field(None, env="EMAIL_USERNAME")
    email_password: Optional[str] = Field(None, env="EMAIL_PASSWORD")
    email_from: Optional[str] = Field(None, env="EMAIL_FROM")
    
    # Webhook Configuration
    webhook_enabled: bool = Field(False, env="WEBHOOK_ENABLED")
    webhook_url: Optional[str] = Field(None, env="WEBHOOK_URL")
    webhook_secret: Optional[str] = Field(None, env="WEBHOOK_SECRET")
    
    # Security
    secret_key: str = Field("your-secret-key-change-in-production", env="SECRET_KEY")
    jwt_secret_key: str = Field("your-jwt-secret-key-change-in-production", env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # Monitoring
    sentry_dsn: Optional[str] = Field(None, env="SENTRY_DSN")
    prometheus_enabled: bool = Field(False, env="PROMETHEUS_ENABLED")
    prometheus_port: int = Field(8000, env="PROMETHEUS_PORT")
    
    # LLM Configuration
    default_llm_provider: str = Field("openai", env="DEFAULT_LLM_PROVIDER")
    default_model: str = Field("gpt-4", env="DEFAULT_MODEL")
    temperature: float = Field(0.1, env="LLM_TEMPERATURE")
    max_tokens: int = Field(4000, env="LLM_MAX_TOKENS")
    
    # Analysis Configuration
    analysis_timeframe: str = Field("1y", env="ANALYSIS_TIMEFRAME")
    technical_indicators: List[str] = Field(
        default=[
            "SMA", "EMA", "RSI", "MACD", "BB", "STOCH", "ADX", "CCI", "WILLR", "MOM"
        ],
        env="TECHNICAL_INDICATORS"
    )
    fundamental_metrics: List[str] = Field(
        default=[
            "PE", "PB", "PS", "PEG", "EV_EBITDA", "ROE", "ROA", "ROIC", "DEBT_EQUITY", "CURRENT_RATIO"
        ],
        env="FUNDAMENTAL_METRICS"
    )
    
    @validator("secret_key")
    def validate_secret_key(cls, v, values):
        """Reject placeholder secret key when not in debug mode."""
        if not values.get("debug", True) and v == "your-secret-key-change-in-production":
            raise ValueError(
                "secret_key must be changed from the default placeholder in production. "
                "Set the SECRET_KEY environment variable."
            )
        return v

    @validator("jwt_secret_key")
    def validate_jwt_secret_key(cls, v, values):
        """Reject placeholder JWT secret key when not in debug mode."""
        if not values.get("debug", True) and v == "your-jwt-secret-key-change-in-production":
            raise ValueError(
                "jwt_secret_key must be changed from the default placeholder in production. "
                "Set the JWT_SECRET_KEY environment variable."
            )
        return v

    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()
    
    @validator("report_format")
    def validate_report_format(cls, v):
        """Validate report format."""
        valid_formats = ["pdf", "html", "json", "csv", "xlsx"]
        if v.lower() not in valid_formats:
            raise ValueError(f"Report format must be one of {valid_formats}")
        return v.lower()
    
    @validator("default_llm_provider")
    def validate_llm_provider(cls, v):
        """Validate LLM provider."""
        valid_providers = ["openai", "anthropic", "ollama", "huggingface"]
        if v.lower() not in valid_providers:
            raise ValueError(f"LLM provider must be one of {valid_providers}")
        return v.lower()
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
