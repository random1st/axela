"""Application entrypoint."""

import structlog
import uvicorn

from axela.config import get_settings


def configure_logging() -> None:
    """Configure structured logging."""
    settings = get_settings()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            (structlog.dev.ConsoleRenderer() if not settings.log_json else structlog.processors.JSONRenderer()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, settings.log_level.upper(), structlog.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def main() -> None:
    """Run the application."""
    configure_logging()
    settings = get_settings()

    logger = structlog.get_logger()
    logger.info(
        "Starting Axela server",
        host=settings.api_host,
        port=settings.api_port,
    )

    uvicorn.run(
        "axela.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
