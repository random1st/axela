"""Tests for Projects API routes."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from axela.api.routes.projects import router
from axela.domain.models import Project


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
def app(mock_project_repo: AsyncMock) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override the dependency
    from axela.api.deps import get_project_repository

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


class TestCreateProject:
    """Tests for POST /api/v1/projects."""

    @pytest.mark.asyncio
    async def test_create_project_success(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        sample_project: Project,
    ) -> None:
        """Test successful project creation."""
        mock_project_repo.get_by_name.return_value = None
        mock_project_repo.create.return_value = sample_project

        response = await client.post(
            "/api/v1/projects",
            json={"name": "Test Project", "color": "#FF5733"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["color"] == "#FF5733"
        mock_project_repo.create.assert_called_once_with(name="Test Project", color="#FF5733")

    @pytest.mark.asyncio
    async def test_create_project_conflict(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        sample_project: Project,
    ) -> None:
        """Test creating project with existing name returns 409."""
        mock_project_repo.get_by_name.return_value = sample_project

        response = await client.post(
            "/api/v1/projects",
            json={"name": "Test Project"},
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_project_without_color(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test creating project without color."""
        project = Project(
            id=uuid4(),
            name="No Color Project",
            color=None,
            created_at=datetime.now(UTC),
        )
        mock_project_repo.get_by_name.return_value = None
        mock_project_repo.create.return_value = project

        response = await client.post(
            "/api/v1/projects",
            json={"name": "No Color Project"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["color"] is None

    @pytest.mark.asyncio
    async def test_create_project_invalid_color(
        self,
        client: AsyncClient,
    ) -> None:
        """Test creating project with invalid color format."""
        response = await client.post(
            "/api/v1/projects",
            json={"name": "Invalid Color", "color": "red"},
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_project_empty_name(
        self,
        client: AsyncClient,
    ) -> None:
        """Test creating project with empty name."""
        response = await client.post(
            "/api/v1/projects",
            json={"name": ""},
        )

        assert response.status_code == 422  # Validation error


class TestListProjects:
    """Tests for GET /api/v1/projects."""

    @pytest.mark.asyncio
    async def test_list_projects_empty(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test listing projects when none exist."""
        mock_project_repo.get_all.return_value = []

        response = await client.get("/api/v1/projects")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_projects_multiple(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test listing multiple projects."""
        projects = [
            Project(
                id=uuid4(),
                name=f"Project {i}",
                color=None,
                created_at=datetime.now(UTC),
            )
            for i in range(3)
        ]
        mock_project_repo.get_all.return_value = projects

        response = await client.get("/api/v1/projects")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


class TestGetProject:
    """Tests for GET /api/v1/projects/{project_id}."""

    @pytest.mark.asyncio
    async def test_get_project_success(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        sample_project: Project,
    ) -> None:
        """Test getting existing project."""
        mock_project_repo.get_by_id.return_value = sample_project

        response = await client.get(f"/api/v1/projects/{sample_project.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_project.id)
        assert data["name"] == sample_project.name

    @pytest.mark.asyncio
    async def test_get_project_not_found(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test getting non-existent project."""
        mock_project_repo.get_by_id.return_value = None

        response = await client.get(f"/api/v1/projects/{uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestUpdateProject:
    """Tests for PATCH /api/v1/projects/{project_id}."""

    @pytest.mark.asyncio
    async def test_update_project_success(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        sample_project: Project,
    ) -> None:
        """Test updating project."""
        mock_project_repo.get_by_name.return_value = None
        updated_project = Project(
            id=sample_project.id,
            name="Updated Name",
            color="#00FF00",
            created_at=sample_project.created_at,
        )
        mock_project_repo.update.return_value = updated_project

        response = await client.patch(
            f"/api/v1/projects/{sample_project.id}",
            json={"name": "Updated Name", "color": "#00FF00"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["color"] == "#00FF00"

    @pytest.mark.asyncio
    async def test_update_project_not_found(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test updating non-existent project."""
        mock_project_repo.get_by_name.return_value = None
        mock_project_repo.update.return_value = None

        response = await client.patch(
            f"/api/v1/projects/{uuid4()}",
            json={"name": "New Name"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_project_name_conflict(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        sample_project: Project,
    ) -> None:
        """Test updating project with conflicting name."""
        conflicting_project = Project(
            id=uuid4(),  # Different ID
            name="Taken Name",
            color=None,
            created_at=datetime.now(UTC),
        )
        mock_project_repo.get_by_name.return_value = conflicting_project

        response = await client.patch(
            f"/api/v1/projects/{sample_project.id}",
            json={"name": "Taken Name"},
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_update_project_same_name_same_project(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
        sample_project: Project,
    ) -> None:
        """Test updating project with its own current name (no conflict)."""
        mock_project_repo.get_by_name.return_value = sample_project
        mock_project_repo.update.return_value = sample_project

        response = await client.patch(
            f"/api/v1/projects/{sample_project.id}",
            json={"name": sample_project.name},
        )

        assert response.status_code == 200


class TestDeleteProject:
    """Tests for DELETE /api/v1/projects/{project_id}."""

    @pytest.mark.asyncio
    async def test_delete_project_success(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test deleting existing project."""
        mock_project_repo.delete.return_value = True

        response = await client.delete(f"/api/v1/projects/{uuid4()}")

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_project_not_found(
        self,
        client: AsyncClient,
        mock_project_repo: AsyncMock,
    ) -> None:
        """Test deleting non-existent project."""
        mock_project_repo.delete.return_value = False

        response = await client.delete(f"/api/v1/projects/{uuid4()}")

        assert response.status_code == 404
