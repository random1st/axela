"""Tests for database session management."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetAsyncEngine:
    """Tests for get_async_engine."""

    def test_creates_engine_with_settings(self) -> None:
        """Test that engine is created with settings from config."""
        from axela.infrastructure.database.session import get_async_engine

        get_async_engine.cache_clear()

        mock_engine = MagicMock()

        with (
            patch("axela.infrastructure.database.session.get_settings") as mock_settings,
            patch(
                "axela.infrastructure.database.session.create_async_engine",
                return_value=mock_engine,
            ) as mock_create,
        ):
            mock_settings.return_value = MagicMock(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                log_level="INFO",
            )

            engine = get_async_engine()

            assert engine is mock_engine
            mock_settings.assert_called_once()
            mock_create.assert_called_once_with(
                "postgresql+asyncpg://user:pass@localhost/db",
                echo=False,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )

        get_async_engine.cache_clear()

    def test_engine_is_cached(self) -> None:
        """Test that engine is cached."""
        from axela.infrastructure.database.session import get_async_engine

        get_async_engine.cache_clear()

        mock_engine = MagicMock()

        with (
            patch("axela.infrastructure.database.session.get_settings") as mock_settings,
            patch(
                "axela.infrastructure.database.session.create_async_engine",
                return_value=mock_engine,
            ),
        ):
            mock_settings.return_value = MagicMock(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                log_level="DEBUG",
            )

            engine1 = get_async_engine()
            engine2 = get_async_engine()

            # Same instance returned
            assert engine1 is engine2
            # Settings only called once due to caching
            mock_settings.assert_called_once()

        get_async_engine.cache_clear()

    def test_engine_with_debug_log_level(self) -> None:
        """Test that engine echoes SQL when DEBUG log level."""
        from axela.infrastructure.database.session import get_async_engine

        get_async_engine.cache_clear()

        mock_engine = MagicMock()

        with (
            patch("axela.infrastructure.database.session.get_settings") as mock_settings,
            patch(
                "axela.infrastructure.database.session.create_async_engine",
                return_value=mock_engine,
            ) as mock_create,
        ):
            mock_settings.return_value = MagicMock(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                log_level="DEBUG",
            )

            get_async_engine()

            # Verify echo=True when DEBUG
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["echo"] is True

        get_async_engine.cache_clear()


class TestGetAsyncSessionFactory:
    """Tests for get_async_session_factory."""

    def test_creates_session_factory(self) -> None:
        """Test that session factory is created."""
        from axela.infrastructure.database.session import (
            get_async_engine,
            get_async_session_factory,
        )

        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()

        mock_engine = MagicMock()
        mock_factory = MagicMock()

        with (
            patch("axela.infrastructure.database.session.get_settings") as mock_settings,
            patch(
                "axela.infrastructure.database.session.create_async_engine",
                return_value=mock_engine,
            ),
            patch(
                "axela.infrastructure.database.session.async_sessionmaker",
                return_value=mock_factory,
            ) as mock_sessionmaker,
        ):
            mock_settings.return_value = MagicMock(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                log_level="INFO",
            )

            factory = get_async_session_factory()

            assert factory is mock_factory
            mock_sessionmaker.assert_called_once()

        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()

    def test_session_factory_is_cached(self) -> None:
        """Test that session factory is cached."""
        from axela.infrastructure.database.session import (
            get_async_engine,
            get_async_session_factory,
        )

        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()

        mock_engine = MagicMock()
        mock_factory = MagicMock()

        with (
            patch("axela.infrastructure.database.session.get_settings") as mock_settings,
            patch(
                "axela.infrastructure.database.session.create_async_engine",
                return_value=mock_engine,
            ),
            patch(
                "axela.infrastructure.database.session.async_sessionmaker",
                return_value=mock_factory,
            ) as mock_sessionmaker,
        ):
            mock_settings.return_value = MagicMock(
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                log_level="INFO",
            )

            factory1 = get_async_session_factory()
            factory2 = get_async_session_factory()

            # Same instance returned
            assert factory1 is factory2
            # Only called once due to caching
            mock_sessionmaker.assert_called_once()

        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()


class TestGetAsyncSession:
    """Tests for get_async_session dependency."""

    @pytest.mark.asyncio
    async def test_yields_session_and_commits(self) -> None:
        """Test that session is yielded and committed on success."""
        from axela.infrastructure.database.session import (
            get_async_engine,
            get_async_session,
            get_async_session_factory,
        )

        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()

        mock_session = AsyncMock()
        mock_factory = MagicMock()

        # Create async context manager mock
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        mock_session_cm.__aexit__.return_value = None
        mock_factory.return_value = mock_session_cm

        with patch(
            "axela.infrastructure.database.session.get_async_session_factory",
            return_value=mock_factory,
        ):
            async for session in get_async_session():
                assert session is mock_session

            mock_session.commit.assert_called_once()
            mock_session.rollback.assert_not_called()

        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self) -> None:
        """Test that session rolls back on exception."""
        from axela.infrastructure.database.session import (
            get_async_engine,
            get_async_session,
            get_async_session_factory,
        )

        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()

        mock_session = AsyncMock()
        mock_factory = MagicMock()

        # Create async context manager mock
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        mock_session_cm.__aexit__.return_value = None
        mock_factory.return_value = mock_session_cm

        with patch(
            "axela.infrastructure.database.session.get_async_session_factory",
            return_value=mock_factory,
        ):
            gen = get_async_session()
            session = await gen.__anext__()
            assert session is mock_session

            # Throw an exception into the generator
            with contextlib.suppress(ValueError):
                await gen.athrow(ValueError, ValueError("Test error"), None)

            mock_session.rollback.assert_called_once()

        get_async_engine.cache_clear()
        get_async_session_factory.cache_clear()
