"""Pytest configuration and fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from axela.infrastructure.database.models import Base

# Set test environment variables before importing settings
os.environ.setdefault("AXELA_TELEGRAM_BOT_TOKEN", "test-bot-token")
os.environ.setdefault("AXELA_ENCRYPTION_KEY", "test-encryption-key-32-bytes-ok")
os.environ.setdefault("AXELA_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession]:
    """Create an async session for testing with in-memory SQLite."""
    # Use SQLite for testing
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()
