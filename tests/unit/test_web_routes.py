"""Tests for web frontend routes."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from axela.domain.enums import DigestType, SourceType
from axela.domain.models import Project, Schedule
from axela.web.routes import api_router, router


@pytest.fixture
def app() -> FastAPI:
    """Create FastAPI app with web routes."""
    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    return app


@pytest.fixture
def mock_project_repo() -> AsyncMock:
    """Create mock project repository."""
    repo = AsyncMock()
    repo.get_all = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_source_repo() -> AsyncMock:
    """Create mock source repository."""
    repo = AsyncMock()
    repo.get_active = AsyncMock(return_value=[])
    repo.get_by_project = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_schedule_repo() -> AsyncMock:
    """Create mock schedule repository."""
    repo = AsyncMock()
    repo.get_active = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_settings_repo() -> AsyncMock:
    """Create mock settings repository."""
    repo = AsyncMock()
    repo.get_all = AsyncMock(return_value=[])
    repo.get = AsyncMock(return_value=None)
    repo.set = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def app_with_mocks(
    app: FastAPI,
    mock_project_repo: AsyncMock,
    mock_source_repo: AsyncMock,
    mock_schedule_repo: AsyncMock,
    mock_settings_repo: AsyncMock,
    mock_session: AsyncMock,
) -> FastAPI:
    """Configure app with mocked dependencies."""
    from axela.api import deps

    app.dependency_overrides[deps.get_project_repository] = lambda: mock_project_repo
    app.dependency_overrides[deps.get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[deps.get_schedule_repository] = lambda: mock_schedule_repo
    app.dependency_overrides[deps.get_settings_repository] = lambda: mock_settings_repo
    app.dependency_overrides[deps.get_session] = lambda: mock_session
    return app


@pytest.fixture
async def client(app_with_mocks: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks),
        base_url="http://test",
    ) as client:
        yield client


class TestDashboardPage:
    """Tests for dashboard page."""

    @pytest.mark.asyncio
    async def test_dashboard_renders(self, client: AsyncClient) -> None:
        """Test dashboard page renders successfully."""
        response = await client.get("/web/")
        assert response.status_code == 200
        assert "Axela" in response.text

    @pytest.mark.asyncio
    async def test_dashboard_shows_stats(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        mock_source_repo: AsyncMock,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test dashboard shows statistics."""
        # Setup mock data using MagicMock to avoid frozen dataclass issues
        project = MagicMock()
        project.id = uuid4()
        project.name = "Test Project"
        project.created_at = datetime.now(UTC)
        mock_project_repo.get_all.return_value = [project]
        mock_source_repo.get_active.return_value = []
        mock_schedule_repo.get_active.return_value = []

        response = await client.get("/web/")
        assert response.status_code == 200
        assert "Проект" in response.text or "проект" in response.text


class TestProjectsPage:
    """Tests for projects page."""

    @pytest.mark.asyncio
    async def test_projects_page_renders(self, client: AsyncClient) -> None:
        """Test projects page renders."""
        response = await client.get("/web/projects")
        assert response.status_code == 200
        assert "Проект" in response.text

    @pytest.mark.asyncio
    async def test_projects_page_shows_empty_state(self, client: AsyncClient) -> None:
        """Test projects page shows empty state when no projects."""
        response = await client.get("/web/projects")
        assert response.status_code == 200
        assert "Нет проектов" in response.text

    @pytest.mark.asyncio
    async def test_projects_page_shows_projects(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test projects page displays projects."""
        mock_project_repo.get_all.return_value = [
            Project(id=uuid4(), name="My Project", color="#FF0000", created_at=datetime.now(UTC)),
        ]

        response = await client.get("/web/projects")
        assert response.status_code == 200
        assert "My Project" in response.text


class TestSourcesPage:
    """Tests for sources page."""

    @pytest.mark.asyncio
    async def test_sources_page_renders(self, client: AsyncClient) -> None:
        """Test sources page renders."""
        response = await client.get("/web/sources")
        assert response.status_code == 200
        assert "Источник" in response.text or "проект" in response.text

    @pytest.mark.asyncio
    async def test_sources_page_filter_by_project(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test sources page filters by project."""
        project_id = uuid4()
        mock_project_repo.get_all.return_value = [
            Project(id=project_id, name="Test Project", created_at=datetime.now(UTC)),
        ]

        response = await client.get(f"/web/sources?project={project_id}")
        assert response.status_code == 200
        mock_source_repo.get_by_project.assert_called_once_with(project_id)


class TestSchedulesPage:
    """Tests for schedules page."""

    @pytest.mark.asyncio
    async def test_schedules_page_renders(self, client: AsyncClient) -> None:
        """Test schedules page renders."""
        response = await client.get("/web/schedules")
        assert response.status_code == 200
        assert "Расписание" in response.text

    @pytest.mark.asyncio
    async def test_schedules_page_shows_cron_help(self, client: AsyncClient) -> None:
        """Test schedules page shows cron expression examples."""
        response = await client.get("/web/schedules")
        assert response.status_code == 200
        assert "Cron" in response.text


class TestSettingsPage:
    """Tests for settings page."""

    @pytest.mark.asyncio
    async def test_settings_page_renders(self, client: AsyncClient) -> None:
        """Test settings page renders."""
        response = await client.get("/web/settings")
        assert response.status_code == 200
        assert "Настройки" in response.text

    @pytest.mark.asyncio
    async def test_settings_page_shows_telegram_section(self, client: AsyncClient) -> None:
        """Test settings page shows Telegram configuration."""
        response = await client.get("/web/settings")
        assert response.status_code == 200
        assert "Telegram" in response.text


class TestProjectsAPI:
    """Tests for projects HTMX API."""

    @pytest.mark.asyncio
    async def test_create_project(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test creating a project via HTMX."""
        created_project = Project(
            id=uuid4(),
            name="New Project",
            color="#00FF00",
            created_at=datetime.now(UTC),
        )
        mock_project_repo.create.return_value = created_project

        response = await client.post(
            "/web/api/projects",
            data={"name": "New Project", "color": "#00FF00"},
        )
        assert response.status_code == 200
        mock_project_repo.create.assert_called_once_with(name="New Project", color="#00FF00")

    @pytest.mark.asyncio
    async def test_update_project(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test updating a project via HTMX."""
        project_id = uuid4()
        updated_project = Project(
            id=project_id,
            name="Updated Name",
            color="#0000FF",
            created_at=datetime.now(UTC),
        )
        mock_project_repo.update.return_value = updated_project

        response = await client.put(
            f"/web/api/projects/{project_id}",
            data={"name": "Updated Name", "color": "#0000FF"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_project_not_found(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test updating non-existent project returns 404."""
        mock_project_repo.update.return_value = None

        response = await client.put(
            f"/web/api/projects/{uuid4()}",
            data={"name": "Test"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test deleting a project via HTMX."""
        project_id = uuid4()

        response = await client.delete(f"/web/api/projects/{project_id}")
        assert response.status_code == 200
        mock_project_repo.delete.assert_called_once_with(project_id)


class TestSourcesAPI:
    """Tests for sources HTMX API."""

    @pytest.mark.asyncio
    async def test_create_source(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test creating a source via HTMX."""
        project_id = uuid4()
        # Use MagicMock because routes.py sets project_name on returned source
        created_source = MagicMock()
        created_source.id = uuid4()
        created_source.project_id = project_id
        created_source.source_type = SourceType.JIRA
        created_source.name = "My Jira"
        created_source.credentials = {"server_url": "https://test.atlassian.net"}
        created_source.is_active = True
        created_source.created_at = datetime.now(UTC)

        mock_source_repo.create.return_value = created_source
        mock_project_repo.get_by_id.return_value = Project(
            id=project_id, name="Test Project", created_at=datetime.now(UTC)
        )

        response = await client.post(
            "/web/api/sources",
            data={
                "project_id": str(project_id),
                "source_type": "jira",
                "name": "My Jira",
                "credentials.server_url": "https://test.atlassian.net",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_source(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test updating a source via HTMX."""
        source_id = uuid4()
        project_id = uuid4()
        # Use MagicMock because routes.py sets project_name on returned source
        updated_source = MagicMock()
        updated_source.id = source_id
        updated_source.project_id = project_id
        updated_source.source_type = SourceType.JIRA
        updated_source.name = "Updated Jira"
        updated_source.credentials = {}
        updated_source.is_active = False
        updated_source.created_at = datetime.now(UTC)

        mock_source_repo.update.return_value = updated_source
        mock_project_repo.get_by_id.return_value = Project(id=project_id, name="Test", created_at=datetime.now(UTC))

        response = await client.put(
            f"/web/api/sources/{source_id}",
            data={"name": "Updated Jira", "is_active": "false"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_source(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test deleting a source via HTMX."""
        source_id = uuid4()

        response = await client.delete(f"/web/api/sources/{source_id}")
        assert response.status_code == 200
        mock_source_repo.delete.assert_called_once_with(source_id)

    @pytest.mark.asyncio
    async def test_test_source_credentials_not_found(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test credential testing for non-existent source."""
        mock_source_repo.get_by_id.return_value = None

        response = await client.post(f"/web/api/sources/{uuid4()}/test")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "not found" in data["error"]


class TestSchedulesAPI:
    """Tests for schedules HTMX API."""

    @pytest.mark.asyncio
    async def test_create_schedule(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test creating a schedule via HTMX."""
        created_schedule = Schedule(
            id=uuid4(),
            name="Morning Digest",
            digest_type=DigestType.MORNING,
            cron_expression="0 9 * * 1-5",
            timezone="UTC",
            is_active=True,
            created_at=datetime.now(UTC),
        )
        mock_schedule_repo.create.return_value = created_schedule

        response = await client.post(
            "/web/api/schedules",
            data={
                "name": "Morning Digest",
                "digest_type": "morning",
                "cron_expression": "0 9 * * 1-5",
                "timezone": "UTC",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_schedule(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test updating a schedule via HTMX."""
        schedule_id = uuid4()
        updated_schedule = Schedule(
            id=schedule_id,
            name="Updated Schedule",
            digest_type=DigestType.EVENING,
            cron_expression="0 18 * * *",
            timezone="Europe/Moscow",
            is_active=True,
            created_at=datetime.now(UTC),
        )
        mock_schedule_repo.update.return_value = updated_schedule

        response = await client.put(
            f"/web/api/schedules/{schedule_id}",
            data={
                "name": "Updated Schedule",
                "digest_type": "evening",
                "cron_expression": "0 18 * * *",
                "timezone": "Europe/Moscow",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_schedule(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test deleting a schedule via HTMX."""
        schedule_id = uuid4()

        response = await client.delete(f"/web/api/schedules/{schedule_id}")
        assert response.status_code == 200
        mock_schedule_repo.delete.assert_called_once_with(schedule_id)


class TestSettingsAPI:
    """Tests for settings HTMX API."""

    @pytest.mark.asyncio
    async def test_create_setting(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test creating a setting via HTMX."""
        response = await client.post(
            "/web/api/settings",
            data={"key": "test.key", "value": "test_value"},
        )
        assert response.status_code == 200
        assert "test.key" in response.text
        mock_settings_repo.set.assert_called_once_with("test.key", "test_value")

    @pytest.mark.asyncio
    async def test_update_setting(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test updating a setting via HTMX."""
        response = await client.put(
            "/web/api/settings/my.setting",
            data={"value": "new_value"},
        )
        assert response.status_code == 200
        mock_settings_repo.set.assert_called_once_with("my.setting", "new_value")

    @pytest.mark.asyncio
    async def test_delete_setting(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test deleting a setting via HTMX."""
        response = await client.delete("/web/api/settings/test.key")
        assert response.status_code == 200
        mock_settings_repo.delete.assert_called_once_with("test.key")

    @pytest.mark.asyncio
    async def test_batch_update_settings(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test batch updating settings via HTMX."""
        response = await client.post(
            "/web/api/settings/batch",
            data={
                "telegram_chat_id": "123456",
                "digest_language": "en",
            },
        )
        assert response.status_code == 200
        assert mock_settings_repo.set.call_count == 2


class TestStatusAPI:
    """Tests for status HTMX API."""

    @pytest.mark.asyncio
    async def test_get_status(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """Test getting system status."""
        response = await client.get("/web/api/status")
        assert response.status_code == 200
        assert "Database" in response.text

    @pytest.mark.asyncio
    async def test_get_status_database_error(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """Test status when database fails."""
        mock_session.execute.side_effect = Exception("Connection failed")

        response = await client.get("/web/api/status")
        assert response.status_code == 200
        # Should still render but show error state
