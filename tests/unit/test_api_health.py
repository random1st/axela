"""Tests for Health API routes."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from axela.api.routes.health import router


@pytest.fixture
def mock_session() -> AsyncMock:
    """Return mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_scheduler() -> MagicMock:
    """Return mock scheduler."""
    scheduler = MagicMock()
    scheduler.is_running = True
    return scheduler


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


class TestHealthCheck:
    """Tests for GET /health."""

    @pytest.mark.asyncio
    async def test_health_check_returns_ok(
        self,
        client: AsyncClient,
    ) -> None:
        """Test basic health check returns ok."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    @pytest.mark.asyncio
    async def test_health_check_includes_version(
        self,
        client: AsyncClient,
    ) -> None:
        """Test health check includes version."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        # Version should be a string
        assert isinstance(data["version"], str)


class TestReadinessCheck:
    """Tests for GET /health/ready."""

    @pytest.mark.asyncio
    async def test_readiness_all_ok(
        self,
        app: FastAPI,
        mock_session: AsyncMock,
        mock_scheduler: MagicMock,
    ) -> None:
        """Test readiness check when all components are healthy."""
        # Override dependencies
        from axela.api.deps import set_scheduler
        from axela.infrastructure.database import get_async_session

        app.dependency_overrides[get_async_session] = lambda: mock_session
        set_scheduler(mock_scheduler)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert data["scheduler"] == "ok"

        # Cleanup
        set_scheduler(None)

    @pytest.mark.asyncio
    async def test_readiness_database_error(
        self,
        app: FastAPI,
        mock_session: AsyncMock,
        mock_scheduler: MagicMock,
    ) -> None:
        """Test readiness check when database fails."""
        mock_session.execute.side_effect = Exception("Database connection failed")

        from axela.api.deps import set_scheduler
        from axela.infrastructure.database import get_async_session

        app.dependency_overrides[get_async_session] = lambda: mock_session
        set_scheduler(mock_scheduler)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert "error" in data["database"]
        assert "Database connection failed" in data["database"]

        # Cleanup
        set_scheduler(None)

    @pytest.mark.asyncio
    async def test_readiness_scheduler_not_configured(
        self,
        app: FastAPI,
        mock_session: AsyncMock,
    ) -> None:
        """Test readiness check when scheduler is not configured."""
        from axela.api.deps import set_scheduler
        from axela.infrastructure.database import get_async_session

        app.dependency_overrides[get_async_session] = lambda: mock_session
        set_scheduler(None)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["scheduler"] == "not configured"

    @pytest.mark.asyncio
    async def test_readiness_scheduler_stopped(
        self,
        app: FastAPI,
        mock_session: AsyncMock,
        mock_scheduler: MagicMock,
    ) -> None:
        """Test readiness check when scheduler is stopped."""
        mock_scheduler.is_running = False

        from axela.api.deps import set_scheduler
        from axela.infrastructure.database import get_async_session

        app.dependency_overrides[get_async_session] = lambda: mock_session
        set_scheduler(mock_scheduler)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["scheduler"] == "stopped"

        # Cleanup
        set_scheduler(None)

    @pytest.mark.asyncio
    async def test_readiness_all_failed(
        self,
        app: FastAPI,
        mock_session: AsyncMock,
    ) -> None:
        """Test readiness check when all components fail."""
        mock_session.execute.side_effect = Exception("DB down")

        from axela.api.deps import set_scheduler
        from axela.infrastructure.database import get_async_session

        app.dependency_overrides[get_async_session] = lambda: mock_session
        set_scheduler(None)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert "error" in data["database"]
        assert data["scheduler"] == "not configured"
