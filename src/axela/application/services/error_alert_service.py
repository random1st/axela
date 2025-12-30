"""Error alerting service for sending collector errors to Telegram."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from axela.domain.events import CollectorFailed
from axela.infrastructure.database.repository import (
    SettingsRepositoryImpl,
    SourceRepositoryImpl,
)
from axela.infrastructure.telegram.bot import DigestBot
from axela.infrastructure.telegram.formatter import format_error_alert

logger = structlog.get_logger()

# Minimum time between alerts for the same source
ALERT_COOLDOWN = timedelta(minutes=30)


class ErrorAlertService:
    """Service for sending collector error alerts to Telegram.

    Features:
    - Subscribes to CollectorFailed events
    - Formats and sends error alerts
    - Deduplicates alerts (rate limiting per source)
    """

    def __init__(
        self,
        bot: DigestBot,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Initialize the error alert service.

        Args:
            bot: Telegram bot for sending alerts
            session_factory: SQLAlchemy async session factory

        """
        self._bot = bot
        self._session_factory = session_factory
        self._last_alerts: dict[UUID, datetime] = {}

    async def handle_collector_failed(self, event: CollectorFailed) -> None:
        """Handle CollectorFailed event by sending alert.

        Args:
            event: The collector failure event

        """
        log = logger.bind(source_id=str(event.source_id), error_type=event.error_type)

        # Check rate limiting
        if not self._should_alert(event.source_id):
            log.debug("Skipping alert due to rate limiting")
            return

        # Get source name and language from database
        async with self._session_factory() as session:
            source_name, language = await self._get_alert_context(session, event.source_id)

        if not source_name:
            log.warning("Source not found for error alert")
            source_name = f"Unknown ({event.source_id})"

        # Format and send alert
        message = format_error_alert(
            source_name=source_name,
            error_type=event.error_type,
            error_message=event.error_message,
            language=language,
        )

        try:
            await self._bot.send_message(message)
            self._last_alerts[event.source_id] = datetime.now(UTC)
            log.info("Error alert sent", source_name=source_name)
        except Exception as e:
            log.exception("Failed to send error alert", error=str(e))

    def _should_alert(self, source_id: UUID) -> bool:
        """Check if we should send an alert for this source.

        Implements rate limiting to avoid spam.

        Args:
            source_id: The source ID to check

        Returns:
            True if alert should be sent

        """
        last_alert = self._last_alerts.get(source_id)
        if last_alert is None:
            return True

        return datetime.now(UTC) - last_alert >= ALERT_COOLDOWN

    async def _get_alert_context(
        self,
        session: AsyncSession,
        source_id: UUID,
    ) -> tuple[str | None, str]:
        """Get source name and language for alert formatting.

        Args:
            session: Database session
            source_id: The source ID

        Returns:
            Tuple of (source_name, language)

        """
        source_repo = SourceRepositoryImpl(session)
        settings_repo = SettingsRepositoryImpl(session)

        # Get source name
        source = await source_repo.get_by_id(source_id)
        source_name = source.name if source else None

        # Get language setting
        language = "ru"  # Default
        lang_setting = await settings_repo.get("digest_language")
        if lang_setting and isinstance(lang_setting.value, str):
            language = lang_setting.value

        return source_name, language

    def clear_rate_limits(self) -> None:
        """Clear all rate limiting state.

        Useful for testing or manual reset.
        """
        self._last_alerts.clear()
