"""Integration tests for repository operations with SQLite in-memory."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import (
    SQLiteCollectorErrorModel,
    SQLiteDigestItemModel,
    SQLiteDigestModel,
    SQLiteItemModel,
    SQLiteProjectModel,
    SQLiteScheduleModel,
    SQLiteSettingModel,
    SQLiteSourceModel,
)


class TestProjectRepository:
    """Integration tests for project repository operations."""

    @pytest.mark.asyncio
    async def test_create_project(self, sqlite_session: AsyncSession) -> None:
        """Test creating a project in the database."""
        project = SQLiteProjectModel(name="Test Project", color="#FF0000")
        sqlite_session.add(project)
        await sqlite_session.flush()

        assert project.id is not None
        assert project.name == "Test Project"
        assert project.color == "#FF0000"
        assert project.created_at is not None

    @pytest.mark.asyncio
    async def test_get_project_by_id(self, sqlite_session: AsyncSession) -> None:
        """Test fetching a project by ID."""
        project = SQLiteProjectModel(name="Fetch Test", color="#00FF00")
        sqlite_session.add(project)
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteProjectModel, project.id)

        assert result is not None
        assert result.name == "Fetch Test"

    @pytest.mark.asyncio
    async def test_get_project_by_name(self, sqlite_session: AsyncSession) -> None:
        """Test fetching a project by name."""
        project = SQLiteProjectModel(name="Name Search", color="#0000FF")
        sqlite_session.add(project)
        await sqlite_session.flush()

        stmt = select(SQLiteProjectModel).where(SQLiteProjectModel.name == "Name Search")
        result = await sqlite_session.execute(stmt)
        found = result.scalar_one_or_none()

        assert found is not None
        assert found.id == project.id

    @pytest.mark.asyncio
    async def test_get_all_projects(self, sqlite_session: AsyncSession) -> None:
        """Test fetching all projects."""
        project1 = SQLiteProjectModel(name="Project A")
        project2 = SQLiteProjectModel(name="Project B")
        sqlite_session.add_all([project1, project2])
        await sqlite_session.flush()

        stmt = select(SQLiteProjectModel).order_by(SQLiteProjectModel.name)
        result = await sqlite_session.execute(stmt)
        projects = list(result.scalars())

        assert len(projects) == 2
        assert projects[0].name == "Project A"
        assert projects[1].name == "Project B"

    @pytest.mark.asyncio
    async def test_update_project(self, sqlite_session: AsyncSession) -> None:
        """Test updating a project."""
        project = SQLiteProjectModel(name="Original Name", color="#111111")
        sqlite_session.add(project)
        await sqlite_session.flush()

        project.name = "Updated Name"
        project.color = "#222222"
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteProjectModel, project.id)
        assert result is not None
        assert result.name == "Updated Name"
        assert result.color == "#222222"

    @pytest.mark.asyncio
    async def test_delete_project(self, sqlite_session: AsyncSession) -> None:
        """Test deleting a project."""
        project = SQLiteProjectModel(name="To Delete")
        sqlite_session.add(project)
        await sqlite_session.flush()
        project_id = project.id

        await sqlite_session.delete(project)
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteProjectModel, project_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_unique_project_name(self, sqlite_session: AsyncSession) -> None:
        """Test that project names must be unique."""
        project1 = SQLiteProjectModel(name="Unique Name")
        sqlite_session.add(project1)
        await sqlite_session.flush()

        project2 = SQLiteProjectModel(name="Unique Name")
        sqlite_session.add(project2)

        with pytest.raises(IntegrityError):
            await sqlite_session.flush()


class TestSourceRepository:
    """Integration tests for source repository operations."""

    @pytest.fixture
    async def project(self, sqlite_session: AsyncSession) -> SQLiteProjectModel:
        """Create a test project."""
        project = SQLiteProjectModel(name="Test Project")
        sqlite_session.add(project)
        await sqlite_session.flush()
        return project

    @pytest.mark.asyncio
    async def test_create_source(self, sqlite_session: AsyncSession, project: SQLiteProjectModel) -> None:
        """Test creating a source."""
        source = SQLiteSourceModel(
            project_id=project.id,
            source_type="jira",
            name="Test Jira",
            credentials={"url": "https://example.atlassian.net"},
            config={"jql": "assignee = me"},
        )
        sqlite_session.add(source)
        await sqlite_session.flush()

        assert source.id is not None
        assert source.is_active is True
        assert source.last_synced_at is None

    @pytest.mark.asyncio
    async def test_get_active_sources(self, sqlite_session: AsyncSession, project: SQLiteProjectModel) -> None:
        """Test fetching active sources."""
        source1 = SQLiteSourceModel(
            project_id=project.id,
            source_type="jira",
            name="Active Source",
            credentials={},
            is_active=True,
        )
        source2 = SQLiteSourceModel(
            project_id=project.id,
            source_type="gmail",
            name="Inactive Source",
            credentials={},
            is_active=False,
        )
        sqlite_session.add_all([source1, source2])
        await sqlite_session.flush()

        stmt = select(SQLiteSourceModel).where(SQLiteSourceModel.is_active == True)  # noqa: E712
        result = await sqlite_session.execute(stmt)
        sources = list(result.scalars())

        assert len(sources) == 1
        assert sources[0].name == "Active Source"

    @pytest.mark.asyncio
    async def test_update_last_synced(self, sqlite_session: AsyncSession, project: SQLiteProjectModel) -> None:
        """Test updating last_synced_at timestamp."""
        source = SQLiteSourceModel(
            project_id=project.id,
            source_type="slack",
            name="Test Slack",
            credentials={},
        )
        sqlite_session.add(source)
        await sqlite_session.flush()

        sync_time = datetime.now(UTC)
        source.last_synced_at = sync_time
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteSourceModel, source.id)
        assert result is not None
        assert result.last_synced_at is not None

    @pytest.mark.asyncio
    async def test_cascade_delete_on_project(self, sqlite_session: AsyncSession, project: SQLiteProjectModel) -> None:
        """Test that sources are deleted when project is deleted."""
        source = SQLiteSourceModel(
            project_id=project.id,
            source_type="gmail",
            name="Test Gmail",
            credentials={},
        )
        sqlite_session.add(source)
        await sqlite_session.flush()
        source_id = source.id

        await sqlite_session.delete(project)
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteSourceModel, source_id)
        assert result is None


class TestItemRepository:
    """Integration tests for item repository operations."""

    @pytest.fixture
    async def source(self, sqlite_session: AsyncSession) -> SQLiteSourceModel:
        """Create a test project and source."""
        project = SQLiteProjectModel(name="Test Project")
        sqlite_session.add(project)
        await sqlite_session.flush()

        source = SQLiteSourceModel(
            project_id=project.id,
            source_type="jira",
            name="Test Jira",
            credentials={},
        )
        sqlite_session.add(source)
        await sqlite_session.flush()
        return source

    @pytest.mark.asyncio
    async def test_create_item(self, sqlite_session: AsyncSession, source: SQLiteSourceModel) -> None:
        """Test creating an item."""
        item = SQLiteItemModel(
            source_id=source.id,
            external_id="PROJ-123",
            item_type="issue",
            title="Test Issue",
            content={"status": "Open", "priority": "High"},
            content_hash="abc123",
            metadata_={"assignee": "john"},
            external_url="https://example.atlassian.net/browse/PROJ-123",
        )
        sqlite_session.add(item)
        await sqlite_session.flush()

        assert item.id is not None
        assert item.fetched_at is not None

    @pytest.mark.asyncio
    async def test_unique_source_external_id(self, sqlite_session: AsyncSession, source: SQLiteSourceModel) -> None:
        """Test that source_id + external_id must be unique."""
        item1 = SQLiteItemModel(
            source_id=source.id,
            external_id="UNIQUE-1",
            item_type="issue",
            content={},
            content_hash="hash1",
        )
        sqlite_session.add(item1)
        await sqlite_session.flush()

        item2 = SQLiteItemModel(
            source_id=source.id,
            external_id="UNIQUE-1",  # Same external_id
            item_type="issue",
            content={},
            content_hash="hash2",
        )
        sqlite_session.add(item2)

        with pytest.raises(IntegrityError):
            await sqlite_session.flush()

    @pytest.mark.asyncio
    async def test_get_items_by_source(self, sqlite_session: AsyncSession, source: SQLiteSourceModel) -> None:
        """Test fetching items by source."""
        item1 = SQLiteItemModel(
            source_id=source.id,
            external_id="ITEM-1",
            item_type="issue",
            content={},
            content_hash="h1",
        )
        item2 = SQLiteItemModel(
            source_id=source.id,
            external_id="ITEM-2",
            item_type="issue",
            content={},
            content_hash="h2",
        )
        sqlite_session.add_all([item1, item2])
        await sqlite_session.flush()

        stmt = select(SQLiteItemModel).where(SQLiteItemModel.source_id == source.id)
        result = await sqlite_session.execute(stmt)
        items = list(result.scalars())

        assert len(items) == 2


class TestDigestRepository:
    """Integration tests for digest repository operations."""

    @pytest.mark.asyncio
    async def test_create_digest(self, sqlite_session: AsyncSession) -> None:
        """Test creating a digest."""
        digest = SQLiteDigestModel(
            digest_type="morning",
            scheduled_at=datetime.now(UTC),
            status="pending",
        )
        sqlite_session.add(digest)
        await sqlite_session.flush()

        assert digest.id is not None
        assert digest.item_count == 0

    @pytest.mark.asyncio
    async def test_update_digest_status(self, sqlite_session: AsyncSession) -> None:
        """Test updating digest status."""
        digest = SQLiteDigestModel(
            digest_type="evening",
            status="pending",
        )
        sqlite_session.add(digest)
        await sqlite_session.flush()

        digest.status = "sent"
        digest.sent_at = datetime.now(UTC)
        digest.telegram_message_id = 12345
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteDigestModel, digest.id)
        assert result is not None
        assert result.status == "sent"
        assert result.telegram_message_id == 12345

    @pytest.mark.asyncio
    async def test_digest_with_items(self, sqlite_session: AsyncSession) -> None:
        """Test creating digest with associated items."""
        # Create project, source, item
        project = SQLiteProjectModel(name="Test")
        sqlite_session.add(project)
        await sqlite_session.flush()

        source = SQLiteSourceModel(
            project_id=project.id,
            source_type="jira",
            name="Jira",
            credentials={},
        )
        sqlite_session.add(source)
        await sqlite_session.flush()

        item = SQLiteItemModel(
            source_id=source.id,
            external_id="TEST-1",
            item_type="issue",
            content={},
            content_hash="hash123",
        )
        sqlite_session.add(item)
        await sqlite_session.flush()

        # Create digest and link item
        digest = SQLiteDigestModel(digest_type="on_demand", status="sent")
        sqlite_session.add(digest)
        await sqlite_session.flush()

        digest_item = SQLiteDigestItemModel(
            digest_id=digest.id,
            item_id=item.id,
            content_hash_at_send="hash123",
        )
        sqlite_session.add(digest_item)
        await sqlite_session.flush()

        # Verify relationship
        stmt = select(SQLiteDigestItemModel).where(SQLiteDigestItemModel.digest_id == digest.id)
        result = await sqlite_session.execute(stmt)
        linked_items = list(result.scalars())

        assert len(linked_items) == 1
        assert linked_items[0].item_id == item.id


class TestSettingRepository:
    """Integration tests for settings repository operations."""

    @pytest.mark.asyncio
    async def test_create_setting(self, sqlite_session: AsyncSession) -> None:
        """Test creating a setting."""
        setting = SQLiteSettingModel(
            key="telegram_chat_id",
            value={"id": 12345},
        )
        sqlite_session.add(setting)
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteSettingModel, "telegram_chat_id")
        assert result is not None
        assert result.value == {"id": 12345}

    @pytest.mark.asyncio
    async def test_update_setting(self, sqlite_session: AsyncSession) -> None:
        """Test updating a setting value."""
        setting = SQLiteSettingModel(
            key="digest_language",
            value={"lang": "en"},
        )
        sqlite_session.add(setting)
        await sqlite_session.flush()

        setting.value = {"lang": "ru"}
        setting.updated_at = datetime.now(UTC)
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteSettingModel, "digest_language")
        assert result is not None
        assert result.value == {"lang": "ru"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_setting(self, sqlite_session: AsyncSession) -> None:
        """Test fetching a nonexistent setting returns None."""
        result = await sqlite_session.get(SQLiteSettingModel, "nonexistent_key")
        assert result is None


class TestScheduleRepository:
    """Integration tests for schedule repository operations."""

    @pytest.mark.asyncio
    async def test_create_schedule(self, sqlite_session: AsyncSession) -> None:
        """Test creating a schedule."""
        schedule = SQLiteScheduleModel(
            name="Morning Digest",
            digest_type="morning",
            cron_expression="0 8 * * *",
            timezone="Europe/Lisbon",
            is_active=True,
            project_ids=[],
        )
        sqlite_session.add(schedule)
        await sqlite_session.flush()

        assert schedule.id is not None

    @pytest.mark.asyncio
    async def test_schedule_with_project_ids(self, sqlite_session: AsyncSession) -> None:
        """Test schedule with project IDs filter."""
        project_id1 = uuid4()
        project_id2 = uuid4()

        schedule = SQLiteScheduleModel(
            name="Filtered Digest",
            digest_type="evening",
            cron_expression="0 19 * * *",
            timezone="UTC",
            project_ids=[project_id1, project_id2],
        )
        sqlite_session.add(schedule)
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteScheduleModel, schedule.id)
        assert result is not None
        assert len(result.project_ids) == 2
        assert project_id1 in result.project_ids

    @pytest.mark.asyncio
    async def test_get_active_schedules(self, sqlite_session: AsyncSession) -> None:
        """Test fetching active schedules."""
        schedule1 = SQLiteScheduleModel(
            name="Active",
            digest_type="morning",
            cron_expression="0 8 * * *",
            is_active=True,
        )
        schedule2 = SQLiteScheduleModel(
            name="Inactive",
            digest_type="evening",
            cron_expression="0 19 * * *",
            is_active=False,
        )
        sqlite_session.add_all([schedule1, schedule2])
        await sqlite_session.flush()

        stmt = select(SQLiteScheduleModel).where(SQLiteScheduleModel.is_active == True)  # noqa: E712
        result = await sqlite_session.execute(stmt)
        schedules = list(result.scalars())

        assert len(schedules) == 1
        assert schedules[0].name == "Active"


class TestCollectorErrorRepository:
    """Integration tests for collector error repository operations."""

    @pytest.fixture
    async def source(self, sqlite_session: AsyncSession) -> SQLiteSourceModel:
        """Create a test project and source."""
        project = SQLiteProjectModel(name="Test Project")
        sqlite_session.add(project)
        await sqlite_session.flush()

        source = SQLiteSourceModel(
            project_id=project.id,
            source_type="jira",
            name="Test Jira",
            credentials={},
        )
        sqlite_session.add(source)
        await sqlite_session.flush()
        return source

    @pytest.mark.asyncio
    async def test_create_error(self, sqlite_session: AsyncSession, source: SQLiteSourceModel) -> None:
        """Test creating a collector error."""
        error = SQLiteCollectorErrorModel(
            source_id=source.id,
            error_type="auth_error",
            error_message="Invalid credentials",
            resolved=False,
        )
        sqlite_session.add(error)
        await sqlite_session.flush()

        assert error.id is not None

    @pytest.mark.asyncio
    async def test_get_unresolved_errors(self, sqlite_session: AsyncSession, source: SQLiteSourceModel) -> None:
        """Test fetching unresolved errors."""
        error1 = SQLiteCollectorErrorModel(
            source_id=source.id,
            error_type="api_error",
            resolved=False,
        )
        error2 = SQLiteCollectorErrorModel(
            source_id=source.id,
            error_type="timeout",
            resolved=True,
        )
        sqlite_session.add_all([error1, error2])
        await sqlite_session.flush()

        stmt = select(SQLiteCollectorErrorModel).where(
            SQLiteCollectorErrorModel.source_id == source.id,
            SQLiteCollectorErrorModel.resolved == False,  # noqa: E712
        )
        result = await sqlite_session.execute(stmt)
        errors = list(result.scalars())

        assert len(errors) == 1
        assert errors[0].error_type == "api_error"

    @pytest.mark.asyncio
    async def test_mark_error_resolved(self, sqlite_session: AsyncSession, source: SQLiteSourceModel) -> None:
        """Test marking an error as resolved."""
        error = SQLiteCollectorErrorModel(
            source_id=source.id,
            error_type="network_error",
            resolved=False,
        )
        sqlite_session.add(error)
        await sqlite_session.flush()

        error.resolved = True
        await sqlite_session.flush()

        result = await sqlite_session.get(SQLiteCollectorErrorModel, error.id)
        assert result is not None
        assert result.resolved is True
