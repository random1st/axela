"""Tests for DigestScheduler."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from axela.domain.enums import DigestType
from axela.domain.models import Schedule
from axela.infrastructure.scheduler.apscheduler import DigestScheduler


class TestDigestScheduler:
    """Tests for DigestScheduler."""

    @pytest.fixture
    def mock_engine(self) -> MagicMock:
        """Return mock SQLAlchemy async engine."""
        return MagicMock()

    @pytest.fixture
    def scheduler(self, mock_engine: MagicMock) -> DigestScheduler:
        """Return DigestScheduler with mocked engine."""
        with (
            patch("axela.infrastructure.scheduler.apscheduler.SQLAlchemyDataStore"),
            patch("axela.infrastructure.scheduler.apscheduler.AsyncpgEventBroker"),
        ):
            return DigestScheduler(mock_engine)

    @pytest.fixture
    def sample_schedule(self) -> Schedule:
        """Return sample schedule."""
        return Schedule(
            id=uuid4(),
            name="Morning Digest",
            digest_type=DigestType.MORNING,
            cron_expression="0 8 * * *",
            timezone="Europe/Lisbon",
            is_active=True,
            project_ids=[],
            created_at=datetime.now(UTC),
        )

    @pytest.fixture
    def mock_job_func(self) -> AsyncMock:
        """Return mock async job function."""
        return AsyncMock()

    def test_init(self, scheduler: DigestScheduler) -> None:
        """Test scheduler initialization."""
        assert scheduler._scheduler is None
        assert scheduler._job_func is None
        assert scheduler.is_running is False

    def test_set_job_function(
        self,
        scheduler: DigestScheduler,
        mock_job_func: AsyncMock,
    ) -> None:
        """Test set_job_function stores the function."""
        scheduler.set_job_function(mock_job_func)
        assert scheduler._job_func == mock_job_func

    @pytest.mark.asyncio
    async def test_start_creates_scheduler(self, scheduler: DigestScheduler) -> None:
        """Test start creates and starts the scheduler."""
        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.__aenter__ = AsyncMock(return_value=mock_async_scheduler)
        mock_async_scheduler.__aexit__ = AsyncMock()
        mock_async_scheduler.start_in_background = AsyncMock()

        with patch(
            "axela.infrastructure.scheduler.apscheduler.AsyncScheduler",
            return_value=mock_async_scheduler,
        ):
            await scheduler.start()

        assert scheduler.is_running is True
        mock_async_scheduler.__aenter__.assert_called_once()
        mock_async_scheduler.start_in_background.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_does_nothing_if_already_running(
        self,
        scheduler: DigestScheduler,
    ) -> None:
        """Test start does nothing if scheduler already running."""
        scheduler._scheduler = MagicMock()  # Simulate already started

        await scheduler.start()

        # Should not have created a new scheduler
        assert scheduler._scheduler is not None

    @pytest.mark.asyncio
    async def test_stop_stops_scheduler(self, scheduler: DigestScheduler) -> None:
        """Test stop method stops the scheduler."""
        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.__aexit__ = AsyncMock()
        scheduler._scheduler = mock_async_scheduler

        await scheduler.stop()

        mock_async_scheduler.__aexit__.assert_called_once_with(None, None, None)
        assert scheduler._scheduler is None
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_stop_does_nothing_if_not_running(
        self,
        scheduler: DigestScheduler,
    ) -> None:
        """Test stop does nothing if scheduler not running."""
        await scheduler.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_add_schedule_requires_running_scheduler(
        self,
        scheduler: DigestScheduler,
        sample_schedule: Schedule,
    ) -> None:
        """Test add_schedule raises if scheduler not started."""
        with pytest.raises(RuntimeError, match="Scheduler not started"):
            await scheduler.add_schedule(sample_schedule)

    @pytest.mark.asyncio
    async def test_add_schedule_requires_job_function(
        self,
        scheduler: DigestScheduler,
        sample_schedule: Schedule,
    ) -> None:
        """Test add_schedule raises if job function not set."""
        scheduler._scheduler = MagicMock()

        with pytest.raises(RuntimeError, match="Job function not set"):
            await scheduler.add_schedule(sample_schedule)

    @pytest.mark.asyncio
    async def test_add_schedule_success(
        self,
        scheduler: DigestScheduler,
        sample_schedule: Schedule,
        mock_job_func: AsyncMock,
    ) -> None:
        """Test add_schedule adds schedule to APScheduler."""
        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.remove_schedule = AsyncMock()
        mock_async_scheduler.add_schedule = AsyncMock()
        scheduler._scheduler = mock_async_scheduler
        scheduler._job_func = mock_job_func

        with patch("axela.infrastructure.scheduler.apscheduler.CronTrigger") as mock_trigger_class:
            mock_trigger = MagicMock()
            mock_trigger_class.from_crontab.return_value = mock_trigger

            await scheduler.add_schedule(sample_schedule)

        mock_async_scheduler.add_schedule.assert_called_once()
        call_kwargs = mock_async_scheduler.add_schedule.call_args.kwargs
        assert call_kwargs["id"] == str(sample_schedule.id)
        assert call_kwargs["kwargs"]["schedule_id"] == sample_schedule.id
        assert call_kwargs["kwargs"]["digest_type"] == "morning"

    @pytest.mark.asyncio
    async def test_add_schedule_inactive_does_not_add(
        self,
        scheduler: DigestScheduler,
        mock_job_func: AsyncMock,
    ) -> None:
        """Test add_schedule does not add inactive schedules."""
        inactive_schedule = Schedule(
            id=uuid4(),
            name="Inactive Digest",
            digest_type=DigestType.MORNING,
            cron_expression="0 8 * * *",
            timezone="Europe/Lisbon",
            is_active=False,
            project_ids=[],
            created_at=datetime.now(UTC),
        )
        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.remove_schedule = AsyncMock()
        mock_async_scheduler.add_schedule = AsyncMock()
        scheduler._scheduler = mock_async_scheduler
        scheduler._job_func = mock_job_func

        await scheduler.add_schedule(inactive_schedule)

        mock_async_scheduler.add_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_schedule_invalid_cron_raises(
        self,
        scheduler: DigestScheduler,
        mock_job_func: AsyncMock,
    ) -> None:
        """Test add_schedule raises on invalid cron expression."""
        invalid_schedule = Schedule(
            id=uuid4(),
            name="Invalid Cron Digest",
            digest_type=DigestType.MORNING,
            cron_expression="invalid cron",
            timezone="Europe/Lisbon",
            is_active=True,
            project_ids=[],
            created_at=datetime.now(UTC),
        )
        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.remove_schedule = AsyncMock()
        scheduler._scheduler = mock_async_scheduler
        scheduler._job_func = mock_job_func

        with (
            patch("axela.infrastructure.scheduler.apscheduler.CronTrigger") as mock_trigger,
            pytest.raises(ValueError),
        ):
            mock_trigger.from_crontab.side_effect = ValueError("Invalid cron")
            await scheduler.add_schedule(invalid_schedule)

    @pytest.mark.asyncio
    async def test_remove_schedule_requires_running_scheduler(
        self,
        scheduler: DigestScheduler,
    ) -> None:
        """Test remove_schedule raises if scheduler not started."""
        with pytest.raises(RuntimeError, match="Scheduler not started"):
            await scheduler.remove_schedule(uuid4())

    @pytest.mark.asyncio
    async def test_remove_schedule_success(
        self,
        scheduler: DigestScheduler,
    ) -> None:
        """Test remove_schedule removes schedule from APScheduler."""
        schedule_id = uuid4()
        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.remove_schedule = AsyncMock()
        scheduler._scheduler = mock_async_scheduler

        await scheduler.remove_schedule(schedule_id)

        mock_async_scheduler.remove_schedule.assert_called_once_with(str(schedule_id))

    @pytest.mark.asyncio
    async def test_remove_schedule_handles_not_found(
        self,
        scheduler: DigestScheduler,
    ) -> None:
        """Test remove_schedule handles schedule not found gracefully."""
        schedule_id = uuid4()
        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.remove_schedule = AsyncMock(side_effect=Exception("Schedule not found"))
        scheduler._scheduler = mock_async_scheduler

        # Should not raise
        await scheduler.remove_schedule(schedule_id)

    @pytest.mark.asyncio
    async def test_sync_schedules_requires_running_scheduler(
        self,
        scheduler: DigestScheduler,
    ) -> None:
        """Test sync_schedules raises if scheduler not started."""
        with pytest.raises(RuntimeError, match="Scheduler not started"):
            await scheduler.sync_schedules([])

    @pytest.mark.asyncio
    async def test_sync_schedules_adds_all_schedules(
        self,
        scheduler: DigestScheduler,
        sample_schedule: Schedule,
        mock_job_func: AsyncMock,
    ) -> None:
        """Test sync_schedules adds all provided schedules."""
        schedule2 = Schedule(
            id=uuid4(),
            name="Evening Digest",
            digest_type=DigestType.EVENING,
            cron_expression="0 19 * * *",
            timezone="Europe/Lisbon",
            is_active=True,
            project_ids=[],
            created_at=datetime.now(UTC),
        )

        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.remove_schedule = AsyncMock()
        mock_async_scheduler.add_schedule = AsyncMock()
        scheduler._scheduler = mock_async_scheduler
        scheduler._job_func = mock_job_func

        with patch("axela.infrastructure.scheduler.apscheduler.CronTrigger") as mock_trigger_class:
            mock_trigger = MagicMock()
            mock_trigger_class.from_crontab.return_value = mock_trigger

            await scheduler.sync_schedules([sample_schedule, schedule2])

        assert mock_async_scheduler.add_schedule.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_schedules_continues_on_error(
        self,
        scheduler: DigestScheduler,
        sample_schedule: Schedule,
        mock_job_func: AsyncMock,
    ) -> None:
        """Test sync_schedules continues even if one schedule fails."""
        schedule2 = Schedule(
            id=uuid4(),
            name="Evening Digest",
            digest_type=DigestType.EVENING,
            cron_expression="0 19 * * *",
            timezone="Europe/Lisbon",
            is_active=True,
            project_ids=[],
            created_at=datetime.now(UTC),
        )

        mock_async_scheduler = AsyncMock()
        mock_async_scheduler.remove_schedule = AsyncMock()
        # First schedule fails, second succeeds
        mock_async_scheduler.add_schedule = AsyncMock(side_effect=[Exception("Failed"), None])
        scheduler._scheduler = mock_async_scheduler
        scheduler._job_func = mock_job_func

        with patch("axela.infrastructure.scheduler.apscheduler.CronTrigger") as mock_trigger_class:
            mock_trigger = MagicMock()
            mock_trigger_class.from_crontab.return_value = mock_trigger

            # Should not raise despite first schedule failing
            await scheduler.sync_schedules([sample_schedule, schedule2])

        # Both schedules should have been attempted
        assert mock_async_scheduler.add_schedule.call_count == 2

    def test_is_running_property(self, scheduler: DigestScheduler) -> None:
        """Test is_running property reflects scheduler state."""
        assert scheduler.is_running is False

        scheduler._scheduler = MagicMock()
        assert scheduler.is_running is True

        scheduler._scheduler = None
        assert scheduler.is_running is False
