"""APScheduler 4 wrapper for digest scheduling."""

import contextlib
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from apscheduler import AsyncScheduler
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.eventbrokers.asyncpg import AsyncpgEventBroker
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncEngine

from axela.domain.models import Schedule

logger = structlog.get_logger()

# Type alias for job functions
JobFunc = Callable[..., Coroutine[Any, Any, None]]


class DigestScheduler:
    """Scheduler wrapper for managing digest schedules with APScheduler 4."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize scheduler with database engine.

        Args:
            engine: SQLAlchemy async engine for PostgreSQL

        """
        self._engine = engine
        self._data_store = SQLAlchemyDataStore(engine)
        self._event_broker = AsyncpgEventBroker.from_async_sqla_engine(engine)
        self._scheduler: AsyncScheduler | None = None
        self._job_func: JobFunc | None = None

    def set_job_function(self, func: JobFunc) -> None:
        """Set the function to call when a schedule triggers.

        Args:
            func: Async function that takes schedule_id, digest_type, project_ids

        """
        self._job_func = func

    async def start(self) -> None:
        """Start the scheduler."""
        if self._scheduler is not None:
            logger.warning("Scheduler already started")
            return

        self._scheduler = AsyncScheduler(
            data_store=self._data_store,
            event_broker=self._event_broker,
        )
        await self._scheduler.__aenter__()
        await self._scheduler.start_in_background()
        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler is None:
            return

        await self._scheduler.__aexit__(None, None, None)
        self._scheduler = None
        logger.info("Scheduler stopped")

    async def add_schedule(self, schedule: Schedule) -> None:
        """Add or update a schedule.

        Args:
            schedule: Schedule domain model

        """
        if self._scheduler is None:
            msg = "Scheduler not started"
            raise RuntimeError(msg)

        if self._job_func is None:
            msg = "Job function not set"
            raise RuntimeError(msg)

        schedule_id = str(schedule.id)

        # Remove existing schedule if it exists
        with contextlib.suppress(Exception):
            await self._scheduler.remove_schedule(schedule_id)

        if not schedule.is_active:
            logger.info("Schedule is inactive, not adding", schedule_id=schedule_id)
            return

        # Create cron trigger with timezone
        try:
            trigger = CronTrigger.from_crontab(
                schedule.cron_expression,
                timezone=ZoneInfo(schedule.timezone),
            )
        except Exception as e:
            logger.exception(
                "Invalid cron expression",
                schedule_id=schedule_id,
                cron=schedule.cron_expression,
                error=str(e),
            )
            raise

        # Add the schedule
        await self._scheduler.add_schedule(
            self._job_func,
            trigger,
            id=schedule_id,
            kwargs={
                "schedule_id": schedule.id,
                "digest_type": schedule.digest_type.value,
                "project_ids": schedule.project_ids,
            },
        )

        logger.info(
            "Schedule added",
            schedule_id=schedule_id,
            name=schedule.name,
            cron=schedule.cron_expression,
            timezone=schedule.timezone,
        )

    async def remove_schedule(self, schedule_id: UUID) -> None:
        """Remove a schedule.

        Args:
            schedule_id: ID of the schedule to remove

        """
        if self._scheduler is None:
            msg = "Scheduler not started"
            raise RuntimeError(msg)

        try:
            await self._scheduler.remove_schedule(str(schedule_id))
            logger.info("Schedule removed", schedule_id=str(schedule_id))
        except Exception as e:
            logger.warning(
                "Failed to remove schedule",
                schedule_id=str(schedule_id),
                error=str(e),
            )

    async def sync_schedules(self, schedules: list[Schedule]) -> None:
        """Sync all schedules from database.

        Removes schedules not in the list and adds/updates those that are.

        Args:
            schedules: List of all active schedules from database

        """
        if self._scheduler is None:
            msg = "Scheduler not started"
            raise RuntimeError(msg)

        # Add/update all schedules
        for schedule in schedules:
            try:
                await self.add_schedule(schedule)
            except Exception as e:
                logger.exception(
                    "Failed to add schedule during sync",
                    schedule_id=str(schedule.id),
                    error=str(e),
                )

        logger.info("Schedules synced", count=len(schedules))

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._scheduler is not None
