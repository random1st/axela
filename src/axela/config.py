"""Configuration management using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, cast

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_default_database_url() -> str:
    """Get default database URL.

    If AXELA_DATABASE_URL is set, use it.
    Otherwise, fall back to SQLite for easy local development.
    """
    env_url = os.environ.get("AXELA_DATABASE_URL")
    if env_url:
        return env_url

    # Default to SQLite in current directory
    db_path = Path.cwd() / "axela.db"
    return f"sqlite+aiosqlite:///{db_path}"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AXELA_",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database (defaults to SQLite if AXELA_DATABASE_URL not set)
    database_url: str = Field(
        default_factory=_get_default_database_url,
        description="Database connection URL (PostgreSQL or SQLite)",
    )

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL database."""
        return "postgresql" in self.database_url or "postgres" in self.database_url

    # Telegram (chat_id is stored in DB settings, configurable via API)
    telegram_bot_token: SecretStr = Field(description="Telegram bot token from @BotFather")

    # Claude API (V2 feature)
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key for AI summarization",
    )

    # Scheduling
    default_timezone: str = Field(
        default="Europe/Lisbon",
        description="Default timezone for schedules",
    )
    morning_digest_time: str = Field(
        default="08:00",
        description="Time for morning digest (HH:MM)",
    )
    evening_digest_time: str = Field(
        default="19:00",
        description="Time for evening digest (HH:MM)",
    )

    # Collector settings
    initial_fetch_days: int = Field(
        default=7,
        description="Days of history to fetch for new sources",
    )

    # Encryption key for storing credentials
    encryption_key: SecretStr = Field(
        description="Fernet encryption key for credentials storage",
    )

    # API settings
    api_host: str = Field(default="127.0.0.1", description="API host")
    api_port: int = Field(default=8000, description="API port")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_json: bool = Field(default=False, description="Use JSON logging format")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Pydantic Settings loads required fields from environment variables.
    We use cast to bypass static type checkers that don't understand this pattern.
    """
    return cast("Settings", Settings.__call__())


# Type alias for dependency injection
SettingsDep = Annotated[Settings, Field(default_factory=get_settings)]
