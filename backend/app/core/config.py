"""Application settings, loaded from environment variables (and `.env` in development).

Settings are validated at startup. Validation errors name the missing or invalid
setting but never echo secret values (backend_spec.md Section 2.4).
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "healthcare-backend"

    # Required: no default, so startup fails clearly when it is missing.
    database_url: SecretStr

    # Comma-separated in the environment, e.g. "http://localhost:5173,https://app.example.com".
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    log_level: str = "INFO"

    # Decided values from the specs; configurable per environment.
    max_upload_mb: int = Field(default=20, gt=0)
    access_token_minutes: int = Field(default=15, gt=0)
    refresh_token_days: int = Field(default=7, gt=0)

    # Authentication (api_contract_spec.md Section 5.1).
    jwt_secret: SecretStr
    jwt_issuer: str = "healthcare-backend"
    cookie_secure: bool = True
    frontend_base_url: str = "http://localhost:5173"
    password_reset_minutes: int = Field(default=30, gt=0)
    login_max_failures: int = Field(default=5, gt=0)
    lockout_minutes: int = Field(default=15, gt=0)

    # Documents (api_contract_spec.md Section 6.1).
    document_storage_dir: str = "storage/documents"
    upload_rate_limit_per_hour: int = Field(default=30, gt=0)

    # AI extraction (DL_AI_spec.md). Off by default: documents are sent to an external provider,
    # so it is an explicit opt-in, for synthetic data only until a privacy review.
    extraction_enabled: bool = False
    groq_api_key: SecretStr | None = None
    ai_model: str = "qwen/qwen3.8-27b"
    extraction_max_attempts: int = Field(default=3, gt=0)
    worker_poll_seconds: float = Field(default=2.0, gt=0)

    # Email: "file" writes messages to dev_mail_dir (development/test only); "ses" for deployment.
    email_backend: Literal["file", "ses"] = "file"
    dev_mail_dir: str = ".dev_mail"

    @field_validator("jwt_secret")
    @classmethod
    def check_jwt_secret_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR")
        return level

    @model_validator(mode="after")
    def check_production_safety(self) -> "Settings":
        if self.is_production:
            if self.log_level == "DEBUG":
                raise ValueError("DEBUG logging is not allowed in production")
            if not self.cors_origins:
                raise ValueError("CORS_ORIGINS must be set in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if self.email_backend == "file":
                raise ValueError("EMAIL_BACKEND=file is for development only")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
