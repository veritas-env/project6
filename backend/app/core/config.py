"""Application settings, read from APP_* environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "TravelEase"

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    # Used for HMAC-signed values (signed links etc.). Required in production.
    secret_key: str = Field(default="", repr=False)

    # Sessions (A07)
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8

    # Login protection (A07)
    login_max_failures: int = 5
    lockout_minutes: int = 15
    login_ip_limit: int = 30
    login_ip_window_seconds: int = 300

    # Uploads (A01/A05)
    upload_dir: str = "./var/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024

    # Alerting (A09)
    alert_failed_login_threshold: int = 10
    alert_authz_denied_threshold: int = 20
    alert_window_minutes: int = 10

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.env == "production":
            if len(self.secret_key) < 32:
                raise ValueError("APP_SECRET_KEY must be at least 32 characters in production")
            if "app:app@" in self.database_url:
                raise ValueError("default database credentials are not allowed in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
