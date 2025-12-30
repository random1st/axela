"""Tests for Sources API routes."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from axela.api.routes.sources import router
from axela.domain.enums import SourceType
from axela.domain.models import Project, Source


@pytest.fixture
def mock_source_repo() -> AsyncMock:
    """Return mock source repository."""
    return AsyncMock()


@pytest.fixture
def mock_project_repo() -> AsyncMock:
    """Return mock project repository."""
    return AsyncMock()


@pytest.fixture
def sample_project() -> Project:
    """Return sample project."""
    return Project(
        id=uuid4(),
        name="Test Project",
        color="#FF5733",
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_source(sample_project: Project) -> Source:
    """Return sample source."""
    return Source(
        id=uuid4(),
        project_id=sample_project.id,
        source_type=SourceType.JIRA,
        name="Test Jira",
        credentials={"api_token": "secret", "email": "test@test.com"},
        config={"project_key": "TEST"},
        is_active=True,
        last_synced_at=None,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def app(mock_source_repo: AsyncMock, mock_project_repo: AsyncMock) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override the dependencies
    from axela.api.deps import get_project_repository, get_source_repository

    app.dependency_overrides[get_source_repository] = lambda: mock_source_repo
    app.dependency_overrides[get_project_repository] = lambda: mock_project_repo

    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


class TestCreateSource:
    """Tests for POST /api/v1/sources."""

    @pytest.mark.asyncio
    async def test_create_source_success(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        mock_project_repo: AsyncMock,
        sample_project: Project,
        sample_source: Source,
    ) -> None:
        """Test successful source creation."""
        mock_project_repo.get_by_id.return_value = sample_project
        mock_source_repo.create.return_value = sample_source

        with patch("axela.api.routes.sources.CollectorRegistry") as mock_registry:
            mock_registry.get.return_value = MagicMock()  # Collector exists

            response = await client.post(
                "/api/v1/sources",
                json={
                    "project_id": str(sample_project.id),
                    "source_type": "jira",
                    "name": "Test Jira",
                    "credentials": {"api_token": "secret", "email": "test@test.com"},
                    "config": {"project_key": "TEST"},
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Jira"
        assert data["source_type"] == "jira"

    @pytest.mark.asyncio
    async def test_create_source_project_not_found(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test creating source with non-existent project."""
        mock_project_repo.get_by_id.return_value = None

        response = await client.post(
            "/api/v1/sources",
            json={
                "project_id": str(uuid4()),
                "source_type": "jira",
                "name": "Test Jira",
                "credentials": {"api_token": "secret"},
            },
        )

        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_source_no_collector_available(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        sample_project: Project,
    ) -> None:
        """Test creating source with unavailable collector type."""
        mock_project_repo.get_by_id.return_value = sample_project

        with patch("axela.api.routes.sources.CollectorRegistry") as mock_registry:
            mock_registry.get.return_value = None  # No collector

            response = await client.post(
                "/api/v1/sources",
                json={
                    "project_id": str(sample_project.id),
                    "source_type": "jira",
                    "name": "Test Jira",
                    "credentials": {"api_token": "secret"},
                },
            )

        assert response.status_code == 400
        assert "No collector available" in response.json()["detail"]


class TestListSources:
    """Tests for GET /api/v1/sources."""

    @pytest.mark.asyncio
    async def test_list_sources_empty(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test listing sources when none exist."""
        mock_source_repo.get_active.return_value = []

        response = await client.get("/api/v1/sources")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_sources_active_only(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test listing only active sources."""
        mock_source_repo.get_active.return_value = [sample_source]

        response = await client.get("/api/v1/sources?active_only=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        mock_source_repo.get_active.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_sources_by_project(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test listing sources by project."""
        mock_source_repo.get_by_project.return_value = [sample_source]

        response = await client.get(f"/api/v1/sources?project_id={sample_source.project_id}")

        assert response.status_code == 200
        mock_source_repo.get_by_project.assert_called_once_with(sample_source.project_id)

    @pytest.mark.asyncio
    async def test_list_sources_by_type(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test listing sources by type."""
        mock_source_repo.get_by_type.return_value = [sample_source]

        response = await client.get("/api/v1/sources?source_type=jira")

        assert response.status_code == 200
        mock_source_repo.get_by_type.assert_called_once_with(SourceType.JIRA)


class TestGetSource:
    """Tests for GET /api/v1/sources/{source_id}."""

    @pytest.mark.asyncio
    async def test_get_source_success(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test getting existing source."""
        mock_source_repo.get_by_id.return_value = sample_source

        response = await client.get(f"/api/v1/sources/{sample_source.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_source.id)
        assert data["name"] == sample_source.name

    @pytest.mark.asyncio
    async def test_get_source_not_found(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test getting non-existent source."""
        mock_source_repo.get_by_id.return_value = None

        response = await client.get(f"/api/v1/sources/{uuid4()}")

        assert response.status_code == 404


class TestUpdateSource:
    """Tests for PATCH /api/v1/sources/{source_id}."""

    @pytest.mark.asyncio
    async def test_update_source_success(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test updating source."""
        updated_source = Source(
            id=sample_source.id,
            project_id=sample_source.project_id,
            source_type=sample_source.source_type,
            name="Updated Name",
            credentials=sample_source.credentials,
            config=sample_source.config,
            is_active=False,
            last_synced_at=sample_source.last_synced_at,
            created_at=sample_source.created_at,
        )
        mock_source_repo.update.return_value = updated_source

        response = await client.patch(
            f"/api/v1/sources/{sample_source.id}",
            json={"name": "Updated Name", "is_active": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_source_not_found(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test updating non-existent source."""
        mock_source_repo.update.return_value = None

        response = await client.patch(
            f"/api/v1/sources/{uuid4()}",
            json={"name": "New Name"},
        )

        assert response.status_code == 404


class TestDeleteSource:
    """Tests for DELETE /api/v1/sources/{source_id}."""

    @pytest.mark.asyncio
    async def test_delete_source_success(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test deleting existing source."""
        mock_source_repo.delete.return_value = True

        response = await client.delete(f"/api/v1/sources/{uuid4()}")

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_source_not_found(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test deleting non-existent source."""
        mock_source_repo.delete.return_value = False

        response = await client.delete(f"/api/v1/sources/{uuid4()}")

        assert response.status_code == 404


class TestSourceCredentials:
    """Tests for POST /api/v1/sources/{source_id}/test."""

    @pytest.mark.asyncio
    async def test_test_credentials_source_not_found(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
    ) -> None:
        """Test credentials for non-existent source."""
        mock_source_repo.get_by_id.return_value = None

        response = await client.post(f"/api/v1/sources/{uuid4()}/test")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_test_credentials_no_collector(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test credentials when no collector available."""
        mock_source_repo.get_by_id.return_value = sample_source

        with patch("axela.api.routes.sources.CollectorRegistry") as mock_registry:
            mock_registry.create.return_value = None

            response = await client.post(f"/api/v1/sources/{sample_source.id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "No collector available" in data["message"]

    @pytest.mark.asyncio
    async def test_test_credentials_valid(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test valid credentials."""
        mock_source_repo.get_by_id.return_value = sample_source

        with patch("axela.api.routes.sources.CollectorRegistry") as mock_registry:
            mock_collector = AsyncMock()
            mock_collector.validate_credentials.return_value = True
            mock_registry.create.return_value = mock_collector

            response = await client.post(f"/api/v1/sources/{sample_source.id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["message"] == "Credentials are valid"
        mock_collector.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_credentials_invalid(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test invalid credentials."""
        mock_source_repo.get_by_id.return_value = sample_source

        with patch("axela.api.routes.sources.CollectorRegistry") as mock_registry:
            mock_collector = AsyncMock()
            mock_collector.validate_credentials.return_value = False
            mock_registry.create.return_value = mock_collector

            response = await client.post(f"/api/v1/sources/{sample_source.id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["message"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_test_credentials_exception(
        self,
        client: AsyncClient,
        mock_source_repo: AsyncMock,
        sample_source: Source,
    ) -> None:
        """Test credentials validation raises exception."""
        mock_source_repo.get_by_id.return_value = sample_source

        with patch("axela.api.routes.sources.CollectorRegistry") as mock_registry:
            mock_collector = AsyncMock()
            mock_collector.validate_credentials.side_effect = Exception("Connection failed")
            mock_registry.create.return_value = mock_collector

            response = await client.post(f"/api/v1/sources/{sample_source.id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "Connection failed" in data["message"]
