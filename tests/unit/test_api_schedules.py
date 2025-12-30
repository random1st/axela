"""Tests for Schedules API routes."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from axela.api.routes.schedules import router
from axela.domain.enums import DigestType
from axela.domain.models import Schedule


@pytest.fixture
def mock_schedule_repo() -> AsyncMock:
    """Return mock schedule repository."""
    return AsyncMock()


@pytest.fixture
def sample_schedule() -> Schedule:
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
def app(mock_schedule_repo: AsyncMock) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override the dependency
    from axela.api.deps import get_schedule_repository

    app.dependency_overrides[get_schedule_repository] = lambda: mock_schedule_repo

    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


class TestCreateSchedule:
    """Tests for POST /api/v1/schedules."""

    @pytest.mark.asyncio
    async def test_create_schedule_success(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
        sample_schedule: Schedule,
    ) -> None:
        """Test successful schedule creation."""
        mock_schedule_repo.create.return_value = sample_schedule

        response = await client.post(
            "/api/v1/schedules",
            json={
                "name": "Morning Digest",
                "digest_type": "morning",
                "cron_expression": "0 8 * * *",
                "timezone": "Europe/Lisbon",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Morning Digest"
        assert data["digest_type"] == "morning"
        assert data["cron_expression"] == "0 8 * * *"

    @pytest.mark.asyncio
    async def test_create_schedule_with_projects(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test creating schedule with project IDs."""
        project_ids = [uuid4(), uuid4()]
        schedule = Schedule(
            id=uuid4(),
            name="Evening Digest",
            digest_type=DigestType.EVENING,
            cron_expression="0 19 * * *",
            timezone="Europe/Lisbon",
            is_active=True,
            project_ids=project_ids,
            created_at=datetime.now(UTC),
        )
        mock_schedule_repo.create.return_value = schedule

        response = await client.post(
            "/api/v1/schedules",
            json={
                "name": "Evening Digest",
                "digest_type": "evening",
                "cron_expression": "0 19 * * *",
                "project_ids": [str(pid) for pid in project_ids],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data["project_ids"]) == 2

    @pytest.mark.asyncio
    async def test_create_schedule_invalid_digest_type(
        self,
        client: AsyncClient,
    ) -> None:
        """Test creating schedule with invalid digest type."""
        response = await client.post(
            "/api/v1/schedules",
            json={
                "name": "Invalid Schedule",
                "digest_type": "invalid_type",
                "cron_expression": "0 8 * * *",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_schedule_empty_name(
        self,
        client: AsyncClient,
    ) -> None:
        """Test creating schedule with empty name."""
        response = await client.post(
            "/api/v1/schedules",
            json={
                "name": "",
                "digest_type": "morning",
                "cron_expression": "0 8 * * *",
            },
        )

        assert response.status_code == 422


class TestListSchedules:
    """Tests for GET /api/v1/schedules."""

    @pytest.mark.asyncio
    async def test_list_schedules_empty(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test listing schedules when none exist."""
        mock_schedule_repo.get_active.return_value = []

        response = await client.get("/api/v1/schedules")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_schedules_multiple(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test listing multiple schedules."""
        schedules = [
            Schedule(
                id=uuid4(),
                name=f"Schedule {i}",
                digest_type=DigestType.MORNING,
                cron_expression=f"0 {8 + i} * * *",
                timezone="Europe/Lisbon",
                is_active=True,
                project_ids=[],
                created_at=datetime.now(UTC),
            )
            for i in range(3)
        ]
        mock_schedule_repo.get_active.return_value = schedules

        response = await client.get("/api/v1/schedules")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


class TestGetSchedule:
    """Tests for GET /api/v1/schedules/{schedule_id}."""

    @pytest.mark.asyncio
    async def test_get_schedule_success(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
        sample_schedule: Schedule,
    ) -> None:
        """Test getting existing schedule."""
        mock_schedule_repo.get_by_id.return_value = sample_schedule

        response = await client.get(f"/api/v1/schedules/{sample_schedule.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_schedule.id)
        assert data["name"] == sample_schedule.name

    @pytest.mark.asyncio
    async def test_get_schedule_not_found(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test getting non-existent schedule."""
        mock_schedule_repo.get_by_id.return_value = None

        response = await client.get(f"/api/v1/schedules/{uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestUpdateSchedule:
    """Tests for PATCH /api/v1/schedules/{schedule_id}."""

    @pytest.mark.asyncio
    async def test_update_schedule_success(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
        sample_schedule: Schedule,
    ) -> None:
        """Test updating schedule."""
        updated_schedule = Schedule(
            id=sample_schedule.id,
            name="Updated Morning Digest",
            digest_type=sample_schedule.digest_type,
            cron_expression="0 9 * * *",
            timezone="UTC",
            is_active=False,
            project_ids=sample_schedule.project_ids,
            created_at=sample_schedule.created_at,
        )
        mock_schedule_repo.update.return_value = updated_schedule

        response = await client.patch(
            f"/api/v1/schedules/{sample_schedule.id}",
            json={
                "name": "Updated Morning Digest",
                "cron_expression": "0 9 * * *",
                "timezone": "UTC",
                "is_active": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Morning Digest"
        assert data["cron_expression"] == "0 9 * * *"
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_schedule_not_found(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test updating non-existent schedule."""
        mock_schedule_repo.update.return_value = None

        response = await client.patch(
            f"/api/v1/schedules/{uuid4()}",
            json={"name": "New Name"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_schedule_project_ids(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
        sample_schedule: Schedule,
    ) -> None:
        """Test updating schedule project IDs."""
        new_project_ids = [uuid4(), uuid4()]
        updated_schedule = Schedule(
            id=sample_schedule.id,
            name=sample_schedule.name,
            digest_type=sample_schedule.digest_type,
            cron_expression=sample_schedule.cron_expression,
            timezone=sample_schedule.timezone,
            is_active=sample_schedule.is_active,
            project_ids=new_project_ids,
            created_at=sample_schedule.created_at,
        )
        mock_schedule_repo.update.return_value = updated_schedule

        response = await client.patch(
            f"/api/v1/schedules/{sample_schedule.id}",
            json={"project_ids": [str(pid) for pid in new_project_ids]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["project_ids"]) == 2


class TestDeleteSchedule:
    """Tests for DELETE /api/v1/schedules/{schedule_id}."""

    @pytest.mark.asyncio
    async def test_delete_schedule_success(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test deleting existing schedule."""
        mock_schedule_repo.delete.return_value = True

        response = await client.delete(f"/api/v1/schedules/{uuid4()}")

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_schedule_not_found(
        self,
        client: AsyncClient,
        mock_schedule_repo: AsyncMock,
    ) -> None:
        """Test deleting non-existent schedule."""
        mock_schedule_repo.delete.return_value = False

        response = await client.delete(f"/api/v1/schedules/{uuid4()}")

        assert response.status_code == 404
