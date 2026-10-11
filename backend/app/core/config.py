"""Application settings, loaded from environment variables (and `.env` in development).

Settings are validated at startup. Validation errors name the missing or invalid
setting but never echo secret values (backend_spec.md Section 2.4).
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

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
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
