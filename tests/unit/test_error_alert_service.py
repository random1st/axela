"""Tests for ErrorAlertService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from axela.application.services.error_alert_service import (
    ALERT_COOLDOWN,
    ErrorAlertService,
)
from axela.domain.events import CollectorFailed


class TestErrorAlertService:
    """Tests for ErrorAlertService."""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Create a mock DigestBot."""
        bot = MagicMock()
        bot.send_message = AsyncMock(return_value=123)
        return bot

    @pytest.fixture
    def mock_session_factory(self) -> MagicMock:
        """Create a mock session factory."""
        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)
        return factory

    @pytest.fixture
    def service(
        self,
        mock_bot: MagicMock,
        mock_session_factory: MagicMock,
    ) -> ErrorAlertService:
        """Create an ErrorAlertService instance."""
        return ErrorAlertService(
            bot=mock_bot,
            session_factory=mock_session_factory,
        )

    @pytest.mark.asyncio
    async def test_handle_collector_failed_sends_alert(
        self,
        service: ErrorAlertService,
        mock_bot: MagicMock,
    ) -> None:
        """Test that collector failure triggers alert."""
        source_id = uuid4()
        event = CollectorFailed(
            source_id=source_id,
            error_type="auth",
            error_message="Token expired",
        )

        with patch.object(
            service,
            "_get_alert_context",
            return_value=("Test Source", "en"),
        ):
            await service.handle_collector_failed(event)

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args[0][0]
        assert "Collector Error" in call_args
        assert "Test Source" in call_args
        assert "auth" in call_args
        assert "Token expired" in call_args

    @pytest.mark.asyncio
    async def test_handle_collector_failed_russian(
        self,
        service: ErrorAlertService,
        mock_bot: MagicMock,
    ) -> None:
        """Test alert in Russian."""
        event = CollectorFailed(
            source_id=uuid4(),
            error_type="api_error",
            error_message="Connection failed",
        )

        with patch.object(
            service,
            "_get_alert_context",
            return_value=("Источник", "ru"),
        ):
            await service.handle_collector_failed(event)

        call_args = mock_bot.send_message.call_args[0][0]
        assert "Ошибка коллектора" in call_args
        assert "Источник" in call_args

    @pytest.mark.asyncio
    async def test_rate_limiting_prevents_duplicate_alerts(
        self,
        service: ErrorAlertService,
        mock_bot: MagicMock,
    ) -> None:
        """Test rate limiting prevents duplicate alerts."""
        source_id = uuid4()
        event = CollectorFailed(
            source_id=source_id,
            error_type="auth",
            error_message="Token expired",
        )

        with patch.object(
            service,
            "_get_alert_context",
            return_value=("Test Source", "en"),
        ):
            # First call should send
            await service.handle_collector_failed(event)
            assert mock_bot.send_message.call_count == 1

            # Second call should be rate limited
            await service.handle_collector_failed(event)
            assert mock_bot.send_message.call_count == 1

    @pytest.mark.asyncio
    async def test_rate_limiting_allows_after_cooldown(
        self,
        service: ErrorAlertService,
        mock_bot: MagicMock,
    ) -> None:
        """Test rate limiting allows alert after cooldown."""
        source_id = uuid4()
        event = CollectorFailed(
            source_id=source_id,
            error_type="auth",
            error_message="Token expired",
        )

        with patch.object(
            service,
            "_get_alert_context",
            return_value=("Test Source", "en"),
        ):
            # First call
            await service.handle_collector_failed(event)
            assert mock_bot.send_message.call_count == 1

            # Simulate time passing
            past_time = datetime.now(UTC) - ALERT_COOLDOWN - timedelta(minutes=1)
            service._last_alerts[source_id] = past_time

            # Second call should now work
            await service.handle_collector_failed(event)
            assert mock_bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_different_sources_not_rate_limited(
        self,
        service: ErrorAlertService,
        mock_bot: MagicMock,
    ) -> None:
        """Test different sources are not rate limited together."""
        source1 = uuid4()
        source2 = uuid4()

        event1 = CollectorFailed(
            source_id=source1,
            error_type="auth",
            error_message="Error 1",
        )
        event2 = CollectorFailed(
            source_id=source2,
            error_type="auth",
            error_message="Error 2",
        )

        with patch.object(
            service,
            "_get_alert_context",
            return_value=("Test Source", "en"),
        ):
            await service.handle_collector_failed(event1)
            await service.handle_collector_failed(event2)

        assert mock_bot.send_message.call_count == 2

    def test_should_alert_first_time(
        self,
        service: ErrorAlertService,
    ) -> None:
        """Test first alert is always allowed."""
        source_id = uuid4()
        assert service._should_alert(source_id) is True

    def test_should_alert_within_cooldown(
        self,
        service: ErrorAlertService,
    ) -> None:
        """Test alert within cooldown is blocked."""
        source_id = uuid4()
        service._last_alerts[source_id] = datetime.now(UTC)
        assert service._should_alert(source_id) is False

    def test_should_alert_after_cooldown(
        self,
        service: ErrorAlertService,
    ) -> None:
        """Test alert after cooldown is allowed."""
        source_id = uuid4()
        service._last_alerts[source_id] = datetime.now(UTC) - ALERT_COOLDOWN - timedelta(seconds=1)
        assert service._should_alert(source_id) is True

    def test_clear_rate_limits(
        self,
        service: ErrorAlertService,
    ) -> None:
        """Test clearing rate limits."""
        source_id = uuid4()
        service._last_alerts[source_id] = datetime.now(UTC)

        assert service._should_alert(source_id) is False

        service.clear_rate_limits()

        assert service._should_alert(source_id) is True

    @pytest.mark.asyncio
    async def test_unknown_source_uses_fallback_name(
        self,
        service: ErrorAlertService,
        mock_bot: MagicMock,
    ) -> None:
        """Test unknown source uses fallback name."""
        source_id = uuid4()
        event = CollectorFailed(
            source_id=source_id,
            error_type="auth",
            error_message="Error",
        )

        with patch.object(
            service,
            "_get_alert_context",
            return_value=(None, "en"),
        ):
            await service.handle_collector_failed(event)

        call_args = mock_bot.send_message.call_args[0][0]
        assert "Unknown" in call_args

    @pytest.mark.asyncio
    async def test_send_failure_is_logged(
        self,
        service: ErrorAlertService,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send failure is logged but doesn't crash."""
        mock_bot.send_message.side_effect = Exception("Network error")

        event = CollectorFailed(
            source_id=uuid4(),
            error_type="auth",
            error_message="Error",
        )

        with patch.object(
            service,
            "_get_alert_context",
            return_value=("Test", "en"),
        ):
            # Should not raise
            await service.handle_collector_failed(event)
