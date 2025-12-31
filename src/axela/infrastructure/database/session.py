"""Database session management."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from axela.config import get_settings


@lru_cache
def get_async_engine() -> AsyncEngine:
    """Get cached async engine.

    Automatically configures for PostgreSQL or SQLite based on database URL.
    """
    settings = get_settings()

    if settings.is_sqlite:
        # SQLite configuration (no connection pooling)
        return create_async_engine(
            settings.database_url,
            echo=settings.log_level == "DEBUG",
            connect_args={"check_same_thread": False},
        )

    # PostgreSQL configuration (with connection pooling)
    return create_async_engine(
        settings.database_url,
        echo=settings.log_level == "DEBUG",
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get cached async session factory."""
    engine = get_async_engine()
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    """Dependency that provides an async database session."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
