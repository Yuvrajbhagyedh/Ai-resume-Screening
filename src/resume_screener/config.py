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
    # Thinking tokens before answering. 0 = off (much faster); negative = model default.
    gemini_thinking_budget: int = 0
    # Extra attempts when Gemini is rate-limited or overloaded (429/503).
    gemini_max_retries: int = 2

    # Candidates whose GitHub lookup and scoring run at the same time. Keep it
    # modest: Gemini's free tier allows only a few requests per minute.
    max_workers: int = 4

    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
