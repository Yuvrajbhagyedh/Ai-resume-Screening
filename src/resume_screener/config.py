"""Runtime configuration, sourced from environment variables / .env only."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_token: str | None = None
    github_enrichment_enabled: bool = True
    github_timeout_seconds: float = 10.0

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 30.0

    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
