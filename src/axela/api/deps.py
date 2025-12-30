"""FastAPI dependencies for dependency injection."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from axela.application.services.error_alert_service import ErrorAlertService
from axela.infrastructure.bus.memory import InMemoryMessageBus
from axela.infrastructure.database.repository import (
    CollectorErrorRepositoryImpl,
    DigestRepositoryImpl,
    ItemRepositoryImpl,
    ProjectRepositoryImpl,
    ScheduleRepositoryImpl,
    SettingsRepositoryImpl,
    SourceRepositoryImpl,
)
from axela.infrastructure.database.session import get_async_session_factory
from axela.infrastructure.scheduler.apscheduler import DigestScheduler
from axela.infrastructure.telegram.bot import DigestBot


# Application state container
class _AppState:
    """Container for application-level state."""

    message_bus: InMemoryMessageBus | None = None
    telegram_bot: DigestBot | None = None
    error_alert_service: ErrorAlertService | None = None
    scheduler: DigestScheduler | None = None


_state = _AppState()


def get_message_bus() -> InMemoryMessageBus:
    """Get the global message bus instance."""
    if _state.message_bus is None:
        msg = "Message bus not initialized"
        raise RuntimeError(msg)
    return _state.message_bus


def set_message_bus(bus: InMemoryMessageBus) -> None:
    """Set the global message bus instance."""
    _state.message_bus = bus


def get_telegram_bot() -> DigestBot | None:
    """Get the Telegram bot instance."""
    return _state.telegram_bot


def set_telegram_bot(bot: DigestBot | None) -> None:
    """Set the Telegram bot instance."""
    _state.telegram_bot = bot


def get_error_alert_service() -> ErrorAlertService | None:
    """Get the error alert service instance."""
    return _state.error_alert_service


def set_error_alert_service(service: ErrorAlertService | None) -> None:
    """Set the error alert service instance."""
    _state.error_alert_service = service


def get_scheduler() -> DigestScheduler | None:
    """Get the scheduler instance."""
    return _state.scheduler


def set_scheduler(scheduler: DigestScheduler | None) -> None:
    """Set the scheduler instance."""
    _state.scheduler = scheduler


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Get database session."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Type aliases for dependency injection
SessionDep = Annotated[AsyncSession, Depends(get_session)]
MessageBusDep = Annotated[InMemoryMessageBus, Depends(get_message_bus)]


# Repository dependencies
def get_project_repository(session: SessionDep) -> ProjectRepositoryImpl:
    """Get project repository."""
    return ProjectRepositoryImpl(session)


def get_source_repository(session: SessionDep) -> SourceRepositoryImpl:
    """Get source repository."""
    return SourceRepositoryImpl(session)


def get_item_repository(session: SessionDep) -> ItemRepositoryImpl:
    """Get item repository."""
    return ItemRepositoryImpl(session)


def get_digest_repository(session: SessionDep) -> DigestRepositoryImpl:
    """Get digest repository."""
    return DigestRepositoryImpl(session)


def get_schedule_repository(session: SessionDep) -> ScheduleRepositoryImpl:
    """Get schedule repository."""
    return ScheduleRepositoryImpl(session)


def get_error_repository(session: SessionDep) -> CollectorErrorRepositoryImpl:
    """Get collector error repository."""
    return CollectorErrorRepositoryImpl(session)


def get_settings_repository(session: SessionDep) -> SettingsRepositoryImpl:
    """Get settings repository."""
    return SettingsRepositoryImpl(session)


# Repository type aliases
ProjectRepoDep = Annotated[ProjectRepositoryImpl, Depends(get_project_repository)]
SourceRepoDep = Annotated[SourceRepositoryImpl, Depends(get_source_repository)]
ItemRepoDep = Annotated[ItemRepositoryImpl, Depends(get_item_repository)]
DigestRepoDep = Annotated[DigestRepositoryImpl, Depends(get_digest_repository)]
ScheduleRepoDep = Annotated[ScheduleRepositoryImpl, Depends(get_schedule_repository)]
ErrorRepoDep = Annotated[CollectorErrorRepositoryImpl, Depends(get_error_repository)]
SettingsRepoDep = Annotated[SettingsRepositoryImpl, Depends(get_settings_repository)]
