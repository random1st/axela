"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, cast

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AXELA_",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Data directory for SQLite and other persistent files
    data_dir: Path = Field(
        default=Path("/data"),
        description="Directory for persistent data (SQLite DB, etc.)",
    )

    # Database (defaults to SQLite in data_dir if not set)
    database_url: str | None = Field(
        default=None,
        description="Database connection URL (PostgreSQL or SQLite). If not set, uses SQLite in data_dir.",
    )

    @model_validator(mode="after")
    def set_default_database_url(self) -> "Settings":
        """Set default database URL if not provided."""
        if self.database_url is None:
            # Ensure data_dir exists
            self.data_dir.mkdir(parents=True, exist_ok=True)
            db_path = self.data_dir / "axela.db"
            object.__setattr__(self, "database_url", f"sqlite+aiosqlite:///{db_path}")
        return self

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        # database_url is always set after model_validator runs
        return self.database_url is not None and self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL database."""
        # database_url is always set after model_validator runs
        if self.database_url is None:
            return False
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
