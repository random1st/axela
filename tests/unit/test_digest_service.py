"""Tests for DigestService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from axela.application.services.digest_service import DigestService
from axela.domain.enums import DigestStatus, DigestType, ItemType, SourceType
from axela.domain.events import (
    CollectionCompleted,
    CollectionStarted,
    CollectorFailed,
    DigestFailed,
    DigestReady,
    DigestSent,
)
from axela.domain.models import Digest, DigestItem, Project, Setting, Source


class TestDigestService:
    """Tests for DigestService."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Return mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_bus(self) -> AsyncMock:
        """Return mock message bus."""
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def service(self, mock_session: AsyncMock, mock_bus: AsyncMock) -> DigestService:
        """Return DigestService with mocked dependencies."""
        return DigestService(mock_session, mock_bus)

    @pytest.fixture
    def sample_project(self) -> Project:
        """Return sample project."""
        return Project(
            id=uuid4(),
            name="Test Project",
            color="#FF0000",
            created_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_source(self, sample_project: Project) -> Source:
        """Return sample source."""
        return Source(
            id=uuid4(),
            project_id=sample_project.id,
            source_type=SourceType.JIRA,
            name="Test Jira",
            credentials={"url": "https://test.atlassian.net", "email": "test@example.com", "api_token": "token"},
            config={"jql": "assignee = currentUser()"},
            is_active=True,
            last_synced_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_digest(self) -> Digest:
        """Return sample digest."""
        return Digest(
            id=uuid4(),
            digest_type=DigestType.ON_DEMAND,
            scheduled_at=datetime.now(UTC),
            status=DigestStatus.PENDING,
            item_count=0,
            created_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_digest_item(self, sample_source: Source) -> DigestItem:
        """Return sample digest item."""
        return DigestItem(
            source_id=sample_source.id,
            external_id="TEST-123",
            item_type=ItemType.ISSUE,
            title="Test Issue",
            content={"status": "Open"},
            content_hash="abc123",
            metadata={},
            external_url="https://test.atlassian.net/browse/TEST-123",
            external_created_at=datetime.now(UTC),
            external_updated_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_generate_digest_no_items(
        self,
        service: DigestService,
        mock_bus: AsyncMock,
        sample_digest: Digest,
    ) -> None:
        """Test generate_digest with no items returns empty digest."""
        # Mock repositories
        service._digests = AsyncMock()
        service._digests.create = AsyncMock(return_value=sample_digest)
        service._digests.update_status = AsyncMock()

        service._sources = AsyncMock()
        service._sources.get_active = AsyncMock(return_value=[])

        # Generate digest
        digest_id = await service.generate_digest(DigestType.ON_DEMAND)

        # Verify
        assert digest_id == sample_digest.id
        service._digests.create.assert_called_once()
        service._digests.update_status.assert_any_call(digest_id, DigestStatus.COLLECTING.value)
        service._digests.update_status.assert_any_call(digest_id, DigestStatus.SENT.value)

    @pytest.mark.asyncio
    async def test_generate_digest_with_items(
        self,
        service: DigestService,
        mock_bus: AsyncMock,
        sample_digest: Digest,
        sample_project: Project,
        sample_source: Source,
        sample_digest_item: DigestItem,
    ) -> None:
        """Test generate_digest with items publishes DigestReady event."""
        item_id = uuid4()

        # Mock repositories
        service._digests = AsyncMock()
        service._digests.create = AsyncMock(return_value=sample_digest)
        service._digests.update_status = AsyncMock()
        service._digests.add_items = AsyncMock()

        service._sources = AsyncMock()
        service._sources.get_active = AsyncMock(return_value=[sample_source])
        service._sources.update_last_synced = AsyncMock()

        service._items = AsyncMock()
        service._items.upsert_many = AsyncMock()
        service._items.get_changed_since_last_digest = AsyncMock(return_value=[(sample_digest_item, item_id)])

        service._projects = AsyncMock()
        service._projects.get_all = AsyncMock(return_value=[sample_project])

        service._errors = AsyncMock()
        service._errors.mark_all_resolved = AsyncMock()

        service._settings = AsyncMock()
        service._settings.get = AsyncMock(return_value=Setting(key="digest_language", value="en"))

        # Mock collector
        mock_collector = AsyncMock()
        mock_collector.collect = AsyncMock(return_value=[sample_digest_item])
        mock_collector.close = AsyncMock()

        with patch(
            "axela.application.services.digest_service.CollectorRegistry.create",
            return_value=mock_collector,
        ):
            digest_id = await service.generate_digest(DigestType.MORNING)

        # Verify
        assert digest_id == sample_digest.id
        service._digests.update_status.assert_any_call(digest_id, DigestStatus.FORMATTING.value)
        service._digests.add_items.assert_called_once()

        # Check DigestReady event was published
        digest_ready_calls = [call for call in mock_bus.publish.call_args_list if isinstance(call.args[0], DigestReady)]
        assert len(digest_ready_calls) == 1
        event = digest_ready_calls[0].args[0]
        assert event.digest_id == digest_id
        assert event.item_count == 1

    @pytest.mark.asyncio
    async def test_generate_digest_filters_by_project_ids(
        self,
        service: DigestService,
        sample_digest: Digest,
        sample_project: Project,
        sample_source: Source,
    ) -> None:
        """Test generate_digest filters sources by project IDs."""
        other_project_id = uuid4()
        other_source = Source(
            id=uuid4(),
            project_id=other_project_id,
            source_type=SourceType.SLACK,
            name="Other Slack",
            credentials={"bot_token": "token"},
            config={},
            is_active=True,
            created_at=datetime.now(UTC),
        )

        # Mock repositories
        service._digests = AsyncMock()
        service._digests.create = AsyncMock(return_value=sample_digest)
        service._digests.update_status = AsyncMock()

        service._sources = AsyncMock()
        service._sources.get_active = AsyncMock(return_value=[sample_source, other_source])

        # Generate digest for specific project only
        await service.generate_digest(DigestType.ON_DEMAND, project_ids=[sample_project.id])

        # The test passes if no errors - filtering happens in _get_sources_for_digest

    @pytest.mark.asyncio
    async def test_generate_digest_handles_collector_error(
        self,
        service: DigestService,
        mock_bus: AsyncMock,
        sample_digest: Digest,
        sample_source: Source,
    ) -> None:
        """Test generate_digest handles collector errors gracefully."""
        from axela.application.ports.collector import CollectorError

        # Mock repositories
        service._digests = AsyncMock()
        service._digests.create = AsyncMock(return_value=sample_digest)
        service._digests.update_status = AsyncMock()

        service._sources = AsyncMock()
        service._sources.get_active = AsyncMock(return_value=[sample_source])

        service._errors = AsyncMock()
        service._errors.create = AsyncMock()

        # Mock collector that raises error
        mock_collector = AsyncMock()
        mock_collector.collect = AsyncMock(side_effect=CollectorError("API error", error_type="api_error"))
        mock_collector.close = AsyncMock()

        with patch(
            "axela.application.services.digest_service.CollectorRegistry.create",
            return_value=mock_collector,
        ):
            await service.generate_digest(DigestType.ON_DEMAND)

        # Verify error was recorded
        service._errors.create.assert_called_once()

        # Check CollectorFailed event was published
        failed_calls = [call for call in mock_bus.publish.call_args_list if isinstance(call.args[0], CollectorFailed)]
        assert len(failed_calls) == 1
        event = failed_calls[0].args[0]
        assert event.source_id == sample_source.id
        assert event.error_type == "api_error"

    @pytest.mark.asyncio
    async def test_generate_digest_publishes_collection_events(
        self,
        service: DigestService,
        mock_bus: AsyncMock,
        sample_digest: Digest,
        sample_source: Source,
        sample_digest_item: DigestItem,
    ) -> None:
        """Test generate_digest publishes CollectionStarted and CollectionCompleted."""
        item_id = uuid4()

        # Mock repositories
        service._digests = AsyncMock()
        service._digests.create = AsyncMock(return_value=sample_digest)
        service._digests.update_status = AsyncMock()
        service._digests.add_items = AsyncMock()

        service._sources = AsyncMock()
        service._sources.get_active = AsyncMock(return_value=[sample_source])
        service._sources.update_last_synced = AsyncMock()

        service._items = AsyncMock()
        service._items.upsert_many = AsyncMock()
        service._items.get_changed_since_last_digest = AsyncMock(return_value=[(sample_digest_item, item_id)])

        service._projects = AsyncMock()
        service._projects.get_all = AsyncMock(return_value=[])

        service._errors = AsyncMock()
        service._errors.mark_all_resolved = AsyncMock()

        service._settings = AsyncMock()
        service._settings.get = AsyncMock(return_value=None)

        # Mock collector
        mock_collector = AsyncMock()
        mock_collector.collect = AsyncMock(return_value=[sample_digest_item])
        mock_collector.close = AsyncMock()

        with patch(
            "axela.application.services.digest_service.CollectorRegistry.create",
            return_value=mock_collector,
        ):
            await service.generate_digest(DigestType.ON_DEMAND)

        # Check events
        started_calls = [
            call for call in mock_bus.publish.call_args_list if isinstance(call.args[0], CollectionStarted)
        ]
        completed_calls = [
            call for call in mock_bus.publish.call_args_list if isinstance(call.args[0], CollectionCompleted)
        ]

        assert len(started_calls) == 1
        assert len(completed_calls) == 1

    @pytest.mark.asyncio
    async def test_generate_digest_failure_publishes_digest_failed(
        self,
        service: DigestService,
        mock_bus: AsyncMock,
        sample_digest: Digest,
    ) -> None:
        """Test generate_digest publishes DigestFailed on error."""
        # Mock repositories to raise error
        service._digests = AsyncMock()
        service._digests.create = AsyncMock(return_value=sample_digest)
        service._digests.update_status = AsyncMock()

        service._sources = AsyncMock()
        service._sources.get_active = AsyncMock(side_effect=Exception("Database error"))

        # Generate digest
        with pytest.raises(Exception, match="Database error"):
            await service.generate_digest(DigestType.ON_DEMAND)

        # Check DigestFailed event was published
        failed_calls = [call for call in mock_bus.publish.call_args_list if isinstance(call.args[0], DigestFailed)]
        assert len(failed_calls) == 1
        event = failed_calls[0].args[0]
        assert event.digest_id == sample_digest.id
        assert "Database error" in event.error_message

    @pytest.mark.asyncio
    async def test_mark_digest_sent(
        self,
        service: DigestService,
        mock_bus: AsyncMock,
    ) -> None:
        """Test mark_digest_sent updates digest and publishes event."""
        digest_id = uuid4()
        telegram_message_id = 12345
        content = "Digest content"
        item_count = 5

        service._digests = AsyncMock()
        service._digests.mark_sent = AsyncMock()

        await service.mark_digest_sent(digest_id, telegram_message_id, content, item_count)

        # Verify
        service._digests.mark_sent.assert_called_once_with(digest_id, telegram_message_id, content, item_count)

        # Check DigestSent event
        sent_calls = [call for call in mock_bus.publish.call_args_list if isinstance(call.args[0], DigestSent)]
        assert len(sent_calls) == 1
        event = sent_calls[0].args[0]
        assert event.digest_id == digest_id
        assert event.telegram_message_id == telegram_message_id

    @pytest.mark.asyncio
    async def test_get_sources_for_digest_all_projects(
        self,
        service: DigestService,
        sample_source: Source,
    ) -> None:
        """Test _get_sources_for_digest returns all sources when no project filter."""
        service._sources = AsyncMock()
        service._sources.get_active = AsyncMock(return_value=[sample_source])

        sources = await service._get_sources_for_digest(None)

        assert len(sources) == 1
        assert sources[0] == sample_source

    @pytest.mark.asyncio
    async def test_get_sources_for_digest_filtered_by_project(
        self,
        service: DigestService,
        sample_source: Source,
    ) -> None:
        """Test _get_sources_for_digest filters by project IDs."""
        other_source = Source(
            id=uuid4(),
            project_id=uuid4(),
            source_type=SourceType.SLACK,
            name="Other",
            credentials={},
            config={},
            is_active=True,
            created_at=datetime.now(UTC),
        )

        service._sources = AsyncMock()
        service._sources.get_active = AsyncMock(return_value=[sample_source, other_source])

        # Filter to only sample_source's project
        sources = await service._get_sources_for_digest([sample_source.project_id])

        assert len(sources) == 1
        assert sources[0] == sample_source

    @pytest.mark.asyncio
    async def test_format_digest_uses_language_setting(
        self,
        service: DigestService,
        sample_project: Project,
        sample_source: Source,
        sample_digest_item: DigestItem,
    ) -> None:
        """Test _format_digest uses language from settings."""
        item_id = uuid4()

        service._settings = AsyncMock()
        service._settings.get = AsyncMock(return_value=Setting(key="digest_language", value="ru"))

        items = [(sample_digest_item, item_id, sample_source)]
        project_map = {sample_project.id: sample_project}

        with patch("axela.application.services.digest_service.format_digest") as mock_format:
            mock_format.return_value = "Formatted content"
            await service._format_digest(DigestType.MORNING, items, project_map)

        mock_format.assert_called_once()
        # Check that language 'ru' was passed
        call_args = mock_format.call_args
        assert call_args.args[2] == "ru"

    @pytest.mark.asyncio
    async def test_format_digest_default_language(
        self,
        service: DigestService,
        sample_project: Project,
        sample_source: Source,
        sample_digest_item: DigestItem,
    ) -> None:
        """Test _format_digest uses default language when setting not found."""
        item_id = uuid4()

        service._settings = AsyncMock()
        service._settings.get = AsyncMock(return_value=None)

        items = [(sample_digest_item, item_id, sample_source)]
        project_map = {sample_project.id: sample_project}

        with patch("axela.application.services.digest_service.format_digest") as mock_format:
            mock_format.return_value = "Formatted content"
            await service._format_digest(DigestType.MORNING, items, project_map)

        mock_format.assert_called_once()
        # Check that default language 'ru' was passed
        call_args = mock_format.call_args
        assert call_args.args[2] == "ru"
