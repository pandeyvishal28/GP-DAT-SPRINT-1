"""
config/settings.py
Centralised configuration loaded from environment variables (.env file).

This file is safe to commit — it contains NO secrets.
Secrets live in the .env file (which is gitignored).

Usage:
    from config.settings import get_settings

    settings = get_settings()
    print(settings.APP_HOST)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Pydantic BaseSettings automatically reads from a .env file and
    validates types.  Every field here maps to a key in .env.example.
    """

    # ── Paths ───────────────────────────────────────────────────────────
    TEMPLATE_DIR: str = Field(
        default="data/templates", description="Directory for GP doc templates"
    )

    SQLITE_DB_PATH: str = Field(
        default="data/gp-dat.db", description="SQLite database file path"
    )

    # ── Application ─────────────────────────────────────────────────────
    APP_HOST: str = Field(default="0.0.0.0", description="Server bind host")
    APP_PORT: int = Field(default=8000, description="Server bind port")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    CORS_ORIGINS: str = Field(default="*", description="Comma-separated CORS origins")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",  # Silently ignore unknown env vars
    }


@lru_cache()
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Uses lru_cache so the .env file is only read once per process.
    Call get_settings.cache_clear() if you need to reload config.
    """
    return Settings()
