"""Unit tests for repository implementations with mocked sessions."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from axela.domain.enums import SourceType
from axela.infrastructure.database.repository import (
    CollectorErrorRepositoryImpl,
    ProjectRepositoryImpl,
    ScheduleRepositoryImpl,
    SettingsRepositoryImpl,
    SourceRepositoryImpl,
)


class TestProjectRepositoryImpl:
    """Tests for ProjectRepositoryImpl."""

    @pytest.fixture
    def session(self) -> AsyncMock:
        """Return mock session."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, session: AsyncMock) -> ProjectRepositoryImpl:
        """Return repository with mock session."""
        return ProjectRepositoryImpl(session)

    @pytest.mark.asyncio
    async def test_create_project(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test creating a project."""
        with patch("axela.infrastructure.database.repository.ProjectModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.id = uuid4()
            mock_model.name = "Test Project"
            mock_model.color = "#FF0000"
            mock_model.created_at = datetime.now(UTC)
            mock_model_class.return_value = mock_model

            project = await repo.create("Test Project", "#FF0000")

            session.add.assert_called_once()
            session.flush.assert_called_once()
            assert project.name == "Test Project"

    @pytest.mark.asyncio
    async def test_get_by_id_found(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting project by ID when found."""
        mock_model = MagicMock()
        mock_model.id = uuid4()
        mock_model.name = "Test Project"
        mock_model.color = None
        mock_model.created_at = datetime.now(UTC)
        session.get.return_value = mock_model

        project = await repo.get_by_id(mock_model.id)

        assert project is not None
        assert project.name == "Test Project"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting project by ID when not found."""
        session.get.return_value = None

        project = await repo.get_by_id(uuid4())

        assert project is None

    @pytest.mark.asyncio
    async def test_get_by_name_found(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting project by name when found."""
        mock_model = MagicMock()
        mock_model.id = uuid4()
        mock_model.name = "Test Project"
        mock_model.color = None
        mock_model.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        session.execute.return_value = mock_result

        project = await repo.get_by_name("Test Project")

        assert project is not None
        assert project.name == "Test Project"

    @pytest.mark.asyncio
    async def test_get_all(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting all projects."""
        mock_models = [
            MagicMock(id=uuid4(), name=f"Project {i}", color=None, created_at=datetime.now(UTC)) for i in range(3)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_models
        session.execute.return_value = mock_result

        projects = await repo.get_all()

        assert len(projects) == 3

    @pytest.mark.asyncio
    async def test_update_found(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test updating project when found."""
        mock_model = MagicMock()
        mock_model.id = uuid4()
        mock_model.name = "Old Name"
        mock_model.color = None
        mock_model.created_at = datetime.now(UTC)
        session.get.return_value = mock_model

        project = await repo.update(mock_model.id, name="New Name", color="#FF0000")

        assert project is not None
        assert mock_model.name == "New Name"
        assert mock_model.color == "#FF0000"
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_not_found(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test updating project when not found."""
        session.get.return_value = None

        project = await repo.update(uuid4(), name="New Name")

        assert project is None

    @pytest.mark.asyncio
    async def test_delete_found(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test deleting project when found."""
        mock_model = MagicMock()
        session.get.return_value = mock_model

        result = await repo.delete(uuid4())

        assert result is True
        session.delete.assert_called_once_with(mock_model)

    @pytest.mark.asyncio
    async def test_delete_not_found(
        self,
        repo: ProjectRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test deleting project when not found."""
        session.get.return_value = None

        result = await repo.delete(uuid4())

        assert result is False


class TestSourceRepositoryImpl:
    """Tests for SourceRepositoryImpl."""

    @pytest.fixture
    def session(self) -> AsyncMock:
        """Return mock session."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, session: AsyncMock) -> SourceRepositoryImpl:
        """Return repository with mock session."""
        return SourceRepositoryImpl(session)

    @pytest.mark.asyncio
    async def test_create_source(
        self,
        repo: SourceRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test creating a source."""
        project_id = uuid4()

        with patch("axela.infrastructure.database.repository.SourceModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.id = uuid4()
            mock_model.project_id = project_id
            mock_model.source_type = "jira"
            mock_model.name = "Test Jira"
            mock_model.credentials = {}
            mock_model.config = {}
            mock_model.is_active = True
            mock_model.last_synced_at = None
            mock_model.created_at = datetime.now(UTC)
            mock_model_class.return_value = mock_model

            source = await repo.create(
                project_id=project_id,
                source_type=SourceType.JIRA,
                name="Test Jira",
                credentials={"token": "secret"},
            )

            session.add.assert_called_once()
            session.flush.assert_called_once()
            assert source.source_type == SourceType.JIRA

    @pytest.mark.asyncio
    async def test_get_active_sources(
        self,
        repo: SourceRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting active sources."""
        mock_models = [
            MagicMock(
                id=uuid4(),
                project_id=uuid4(),
                source_type="jira",
                name="Test",
                credentials={},
                config={},
                is_active=True,
                last_synced_at=None,
                created_at=datetime.now(UTC),
            )
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_models
        session.execute.return_value = mock_result

        sources = await repo.get_active()

        assert len(sources) == 1

    @pytest.mark.asyncio
    async def test_get_by_type(
        self,
        repo: SourceRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting sources by type."""
        mock_models = [
            MagicMock(
                id=uuid4(),
                project_id=uuid4(),
                source_type="jira",
                name="Test",
                credentials={},
                config={},
                is_active=True,
                last_synced_at=None,
                created_at=datetime.now(UTC),
            )
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_models
        session.execute.return_value = mock_result

        sources = await repo.get_by_type(SourceType.JIRA)

        assert len(sources) == 1

    @pytest.mark.asyncio
    async def test_update_source(
        self,
        repo: SourceRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test updating source."""
        mock_model = MagicMock()
        mock_model.id = uuid4()
        mock_model.project_id = uuid4()
        mock_model.source_type = "jira"
        mock_model.name = "Old Name"
        mock_model.credentials = {}
        mock_model.config = {}
        mock_model.is_active = True
        mock_model.last_synced_at = None
        mock_model.created_at = datetime.now(UTC)
        session.get.return_value = mock_model

        source = await repo.update(mock_model.id, name="New Name", is_active=False)

        assert source is not None
        assert mock_model.name == "New Name"
        assert mock_model.is_active is False


class TestScheduleRepositoryImpl:
    """Tests for ScheduleRepositoryImpl."""

    @pytest.fixture
    def session(self) -> AsyncMock:
        """Return mock session."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, session: AsyncMock) -> ScheduleRepositoryImpl:
        """Return repository with mock session."""
        return ScheduleRepositoryImpl(session)

    @pytest.mark.asyncio
    async def test_create_schedule(
        self,
        repo: ScheduleRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test creating a schedule."""
        with patch("axela.infrastructure.database.repository.ScheduleModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.id = uuid4()
            mock_model.name = "Morning Digest"
            mock_model.digest_type = "morning"
            mock_model.cron_expression = "0 8 * * *"
            mock_model.timezone = "Europe/Lisbon"
            mock_model.is_active = True
            mock_model.project_ids = []
            mock_model.created_at = datetime.now(UTC)
            mock_model_class.return_value = mock_model

            schedule = await repo.create(
                name="Morning Digest",
                digest_type="morning",
                cron_expression="0 8 * * *",
                timezone="Europe/Lisbon",
            )

            session.add.assert_called_once()
            session.flush.assert_called_once()
            assert schedule.name == "Morning Digest"

    @pytest.mark.asyncio
    async def test_get_active_schedules(
        self,
        repo: ScheduleRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting active schedules."""
        mock_models = [
            MagicMock(
                id=uuid4(),
                name="Schedule",
                digest_type="morning",
                cron_expression="0 8 * * *",
                timezone="UTC",
                is_active=True,
                project_ids=[],
                created_at=datetime.now(UTC),
            )
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_models
        session.execute.return_value = mock_result

        schedules = await repo.get_active()

        assert len(schedules) == 1


class TestSettingsRepositoryImpl:
    """Tests for SettingsRepositoryImpl."""

    @pytest.fixture
    def session(self) -> AsyncMock:
        """Return mock session."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, session: AsyncMock) -> SettingsRepositoryImpl:
        """Return repository with mock session."""
        return SettingsRepositoryImpl(session)

    @pytest.mark.asyncio
    async def test_get_setting(
        self,
        repo: SettingsRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting a setting."""
        mock_model = MagicMock()
        mock_model.key = "telegram_chat_id"
        mock_model.value = 123456
        mock_model.updated_at = datetime.now(UTC)
        session.get.return_value = mock_model

        setting = await repo.get("telegram_chat_id")

        assert setting is not None
        assert setting.value == 123456

    @pytest.mark.asyncio
    async def test_set_creates_new(
        self,
        repo: SettingsRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test setting a new value."""
        session.get.return_value = None

        with patch("axela.infrastructure.database.repository.SettingModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.key = "new_key"
            mock_model.value = "new_value"
            mock_model.updated_at = datetime.now(UTC)
            mock_model_class.return_value = mock_model

            setting = await repo.set("new_key", "new_value")

            session.add.assert_called_once()
            assert setting.key == "new_key"

    @pytest.mark.asyncio
    async def test_set_updates_existing(
        self,
        repo: SettingsRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test updating an existing setting."""
        mock_model = MagicMock()
        mock_model.key = "existing_key"
        mock_model.value = "old_value"
        mock_model.updated_at = datetime.now(UTC)
        session.get.return_value = mock_model

        await repo.set("existing_key", "new_value")

        assert mock_model.value == "new_value"
        session.add.assert_not_called()


class TestCollectorErrorRepositoryImpl:
    """Tests for CollectorErrorRepositoryImpl."""

    @pytest.fixture
    def session(self) -> AsyncMock:
        """Return mock session."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, session: AsyncMock) -> CollectorErrorRepositoryImpl:
        """Return repository with mock session."""
        return CollectorErrorRepositoryImpl(session)

    @pytest.mark.asyncio
    async def test_create_error(
        self,
        repo: CollectorErrorRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test creating an error."""
        source_id = uuid4()

        with patch("axela.infrastructure.database.repository.CollectorErrorModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model.id = uuid4()
            mock_model.source_id = source_id
            mock_model.error_type = "ConnectionError"
            mock_model.error_message = "Failed"
            mock_model.is_resolved = False
            mock_model.created_at = datetime.now(UTC)
            mock_model_class.return_value = mock_model

            error = await repo.create(
                source_id=source_id,
                error_type="ConnectionError",
                error_message="Failed",
            )

            session.add.assert_called_once()
            session.flush.assert_called_once()
            assert error.error_type == "ConnectionError"

    @pytest.mark.asyncio
    async def test_get_unresolved(
        self,
        repo: CollectorErrorRepositoryImpl,
        session: AsyncMock,
    ) -> None:
        """Test getting unresolved errors."""
        source_id = uuid4()
        mock_models = [
            MagicMock(
                id=uuid4(),
                source_id=source_id,
                error_type="Error",
                error_message="Test",
                is_resolved=False,
                resolved_at=None,
                created_at=datetime.now(UTC),
            )
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_models
        session.execute.return_value = mock_result

        errors = await repo.get_unresolved(source_id)

        assert len(errors) == 1
