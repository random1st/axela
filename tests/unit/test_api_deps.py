"""Tests for FastAPI dependencies."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axela.api.deps import (
    _AppState,
    get_error_alert_service,
    get_message_bus,
    get_scheduler,
    get_telegram_bot,
    set_error_alert_service,
    set_message_bus,
    set_scheduler,
    set_telegram_bot,
)


class TestAppState:
    """Tests for application state management."""

    def test_initial_state_is_none(self) -> None:
        """Test that initial state values are None."""
        state = _AppState()
        assert state.message_bus is None
        assert state.telegram_bot is None
        assert state.error_alert_service is None
        assert state.scheduler is None


class TestMessageBus:
    """Tests for message bus getter/setter."""

    def test_get_message_bus_not_initialized(self) -> None:
        """Test getting message bus when not initialized raises."""
        set_message_bus(None)  # type: ignore[arg-type]

        with pytest.raises(RuntimeError, match="Message bus not initialized"):
            get_message_bus()

    def test_set_and_get_message_bus(self) -> None:
        """Test setting and getting message bus."""
        mock_bus = MagicMock()
        set_message_bus(mock_bus)

        result = get_message_bus()
        assert result == mock_bus

        # Cleanup
        set_message_bus(None)  # type: ignore[arg-type]


class TestTelegramBot:
    """Tests for telegram bot getter/setter."""

    def test_get_telegram_bot_none(self) -> None:
        """Test getting telegram bot when not set returns None."""
        set_telegram_bot(None)
        result = get_telegram_bot()
        assert result is None

    def test_set_and_get_telegram_bot(self) -> None:
        """Test setting and getting telegram bot."""
        mock_bot = MagicMock()
        set_telegram_bot(mock_bot)

        result = get_telegram_bot()
        assert result == mock_bot

        # Cleanup
        set_telegram_bot(None)


class TestErrorAlertService:
    """Tests for error alert service getter/setter."""

    def test_get_error_alert_service_none(self) -> None:
        """Test getting error alert service when not set returns None."""
        set_error_alert_service(None)
        result = get_error_alert_service()
        assert result is None

    def test_set_and_get_error_alert_service(self) -> None:
        """Test setting and getting error alert service."""
        mock_service = MagicMock()
        set_error_alert_service(mock_service)

        result = get_error_alert_service()
        assert result == mock_service

        # Cleanup
        set_error_alert_service(None)


class TestScheduler:
    """Tests for scheduler getter/setter."""

    def test_get_scheduler_none(self) -> None:
        """Test getting scheduler when not set returns None."""
        set_scheduler(None)
        result = get_scheduler()
        assert result is None

    def test_set_and_get_scheduler(self) -> None:
        """Test setting and getting scheduler."""
        mock_scheduler = MagicMock()
        set_scheduler(mock_scheduler)

        result = get_scheduler()
        assert result == mock_scheduler

        # Cleanup
        set_scheduler(None)


class TestGetSession:
    """Tests for database session dependency."""

    @pytest.mark.asyncio
    async def test_get_session_commit_on_success(self) -> None:
        """Test session commits on successful operations."""
        mock_session = AsyncMock()

        with patch("axela.api.deps.get_async_session_factory") as mock_factory:
            mock_session_cm = AsyncMock()
            mock_session_cm.__aenter__.return_value = mock_session
            mock_session_cm.__aexit__.return_value = None
            mock_factory.return_value = MagicMock(return_value=mock_session_cm)

            from axela.api.deps import get_session

            async for _session in get_session():
                # Use the session
                pass

            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_rollback_on_exception(self) -> None:
        """Test session rolls back on exception."""
        mock_session = AsyncMock()

        with patch("axela.api.deps.get_async_session_factory") as mock_factory:
            mock_session_cm = AsyncMock()
            mock_session_cm.__aenter__.return_value = mock_session
            mock_session_cm.__aexit__.return_value = None
            mock_factory.return_value = MagicMock(return_value=mock_session_cm)

            from axela.api.deps import get_session

            gen = get_session()
            try:
                await gen.__anext__()
                # Simulate an exception
                raise ValueError("Test error")
            except ValueError:
                # Cleanup the generator by throwing into it
                with contextlib.suppress(ValueError):
                    await gen.athrow(ValueError, ValueError("Test error"), None)

            mock_session.rollback.assert_called_once()


class TestRepositoryDependencies:
    """Tests for repository dependency functions."""

    def test_get_project_repository(self) -> None:
        """Test project repository dependency creation."""
        mock_session = MagicMock()

        from axela.api.deps import get_project_repository
        from axela.infrastructure.database.repository import ProjectRepositoryImpl

        result = get_project_repository(mock_session)

        assert isinstance(result, ProjectRepositoryImpl)

    def test_get_source_repository(self) -> None:
        """Test source repository dependency creation."""
        mock_session = MagicMock()

        from axela.api.deps import get_source_repository
        from axela.infrastructure.database.repository import SourceRepositoryImpl

        result = get_source_repository(mock_session)

        assert isinstance(result, SourceRepositoryImpl)

    def test_get_item_repository(self) -> None:
        """Test item repository dependency creation."""
        mock_session = MagicMock()

        from axela.api.deps import get_item_repository
        from axela.infrastructure.database.repository import ItemRepositoryImpl

        result = get_item_repository(mock_session)

        assert isinstance(result, ItemRepositoryImpl)

    def test_get_digest_repository(self) -> None:
        """Test digest repository dependency creation."""
        mock_session = MagicMock()

        from axela.api.deps import get_digest_repository
        from axela.infrastructure.database.repository import DigestRepositoryImpl

        result = get_digest_repository(mock_session)

        assert isinstance(result, DigestRepositoryImpl)

    def test_get_schedule_repository(self) -> None:
        """Test schedule repository dependency creation."""
        mock_session = MagicMock()

        from axela.api.deps import get_schedule_repository
        from axela.infrastructure.database.repository import ScheduleRepositoryImpl

        result = get_schedule_repository(mock_session)

        assert isinstance(result, ScheduleRepositoryImpl)

    def test_get_error_repository(self) -> None:
        """Test collector error repository dependency creation."""
        mock_session = MagicMock()

        from axela.api.deps import get_error_repository
        from axela.infrastructure.database.repository import CollectorErrorRepositoryImpl

        result = get_error_repository(mock_session)

        assert isinstance(result, CollectorErrorRepositoryImpl)

    def test_get_settings_repository(self) -> None:
        """Test settings repository dependency creation."""
        mock_session = MagicMock()

        from axela.api.deps import get_settings_repository
        from axela.infrastructure.database.repository import SettingsRepositoryImpl

        result = get_settings_repository(mock_session)

        assert isinstance(result, SettingsRepositoryImpl)
