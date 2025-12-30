"""FastAPI application factory."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from axela import __version__
from axela.application.services.error_alert_service import ErrorAlertService
from axela.config import get_settings
from axela.domain.events import CollectorFailed, Event
from axela.infrastructure.bus.memory import InMemoryMessageBus
from axela.infrastructure.database.repository import SettingsRepositoryImpl
from axela.infrastructure.database.session import get_async_session_factory
from axela.infrastructure.telegram.bot import DigestBot
from axela.web.routes import api_router as web_api_router
from axela.web.routes import router as web_router

from .deps import (
    set_error_alert_service,
    set_message_bus,
    set_telegram_bot,
)
from .routes import health, projects, schedules, settings, sources

# Type alias to work around Starlette type system issue
_CORSMiddleware: Any = CORSMiddleware

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager."""
    app_settings = get_settings()

    logger.info(
        "Starting Axela",
        version=__version__,
        api_host=app_settings.api_host,
        api_port=app_settings.api_port,
    )

    # Initialize message bus
    message_bus = InMemoryMessageBus()
    await message_bus.start()
    set_message_bus(message_bus)
    logger.info("Message bus started")

    # Initialize Telegram bot if token is configured
    bot: DigestBot | None = None
    error_service: ErrorAlertService | None = None

    if app_settings.telegram_bot_token:
        bot = DigestBot(app_settings.telegram_bot_token.get_secret_value())
        set_telegram_bot(bot)

        # Get chat_id from settings if available
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            settings_repo = SettingsRepositoryImpl(session)
            chat_id_setting = await settings_repo.get("telegram_chat_id")
            if chat_id_setting and isinstance(chat_id_setting.value, int):
                bot.set_chat_id(chat_id_setting.value)

        await bot.start()
        logger.info("Telegram bot started")

        # Initialize error alert service
        error_service = ErrorAlertService(
            bot=bot,
            session_factory=session_factory,
        )
        set_error_alert_service(error_service)

        # Subscribe to collector failures
        message_bus.subscribe(
            CollectorFailed,
            cast(
                "Callable[[Event], Awaitable[None]]",
                error_service.handle_collector_failed,
            ),
        )
        logger.info("Error alert service initialized")
    else:
        logger.warning("Telegram bot token not configured, alerts disabled")

    yield

    # Cleanup
    logger.info("Shutting down Axela")

    if bot is not None:
        await bot.stop()
        logger.info("Telegram bot stopped")

    await message_bus.stop()
    logger.info("Message bus stopped")

    set_telegram_bot(None)
    set_error_alert_service(None)


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Axela",
        description="Personal digest bot aggregating updates from work tools",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        _CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    app.include_router(health.router)
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(sources.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")
    app.include_router(schedules.router, prefix="/api/v1")

    # Include Web frontend routers
    app.include_router(web_router)
    app.include_router(web_api_router)

    return app


# Application instance for uvicorn
app = create_app()
