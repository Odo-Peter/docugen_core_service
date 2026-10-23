"""
Application settings, loaded from environment variables (see .env.example).

Kept as one Settings object rather than scattered os.environ calls so every
limit referenced in the API contract (ADR 0001 / api-contract.md) has a
single, greppable source.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "info"

    database_url: str = "postgresql+psycopg://docgen:docgen@localhost:5432/docgen"

    max_request_body_bytes: int = 5 * 1024 * 1024
    max_template_bytes: int = 1 * 1024 * 1024
    render_timeout_seconds: int = 30

    # TODO(step 4 — page-cap benchmark): set the real value and remove the
    # startup guard in main.py that currently refuses to boot in production
    # with page_limit == 0.
    page_limit: int = 5
    rate_limit_per_minute: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
