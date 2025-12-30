"""Tests for Settings API routes."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from axela.api.routes.settings import router
from axela.domain.models import Setting


@pytest.fixture
def mock_settings_repo() -> AsyncMock:
    """Return mock settings repository."""
    return AsyncMock()


@pytest.fixture
def sample_setting() -> Setting:
    """Return sample setting."""
    return Setting(
        key="telegram_chat_id",
        value=123456789,
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def app(mock_settings_repo: AsyncMock) -> FastAPI:
    """Create test FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override the dependency
    from axela.api.deps import get_settings_repository

    app.dependency_overrides[get_settings_repository] = lambda: mock_settings_repo

    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


class TestListSettings:
    """Tests for GET /api/v1/settings."""

    @pytest.mark.asyncio
    async def test_list_settings_empty(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test listing settings when none exist."""
        mock_settings_repo.get_all.return_value = []

        response = await client.get("/api/v1/settings")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_settings_multiple(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test listing multiple settings."""
        settings = [
            Setting(key="telegram_chat_id", value=123456789, updated_at=datetime.now(UTC)),
            Setting(key="digest_language", value="ru", updated_at=datetime.now(UTC)),
            Setting(key="theme", value="dark", updated_at=datetime.now(UTC)),
        ]
        mock_settings_repo.get_all.return_value = settings

        response = await client.get("/api/v1/settings")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        keys = [s["key"] for s in data]
        assert "telegram_chat_id" in keys
        assert "digest_language" in keys

    @pytest.mark.asyncio
    async def test_list_settings_with_various_types(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test listing settings with various value types."""
        settings = [
            Setting(key="int_setting", value=42, updated_at=datetime.now(UTC)),
            Setting(key="str_setting", value="text", updated_at=datetime.now(UTC)),
            Setting(key="bool_setting", value=True, updated_at=datetime.now(UTC)),
            Setting(key="list_setting", value=[1, 2, 3], updated_at=datetime.now(UTC)),
            Setting(key="dict_setting", value={"nested": "value"}, updated_at=datetime.now(UTC)),
        ]
        mock_settings_repo.get_all.return_value = settings

        response = await client.get("/api/v1/settings")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

        # Verify types are preserved
        int_setting = next(s for s in data if s["key"] == "int_setting")
        assert int_setting["value"] == 42

        list_setting = next(s for s in data if s["key"] == "list_setting")
        assert list_setting["value"] == [1, 2, 3]

        dict_setting = next(s for s in data if s["key"] == "dict_setting")
        assert dict_setting["value"] == {"nested": "value"}


class TestGetSetting:
    """Tests for GET /api/v1/settings/{key}."""

    @pytest.mark.asyncio
    async def test_get_setting_success(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
        sample_setting: Setting,
    ) -> None:
        """Test getting existing setting."""
        mock_settings_repo.get.return_value = sample_setting

        response = await client.get("/api/v1/settings/telegram_chat_id")

        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "telegram_chat_id"
        assert data["value"] == 123456789
        mock_settings_repo.get.assert_called_once_with("telegram_chat_id")

    @pytest.mark.asyncio
    async def test_get_setting_not_found(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test getting non-existent setting."""
        mock_settings_repo.get.return_value = None

        response = await client.get("/api/v1/settings/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_setting_with_special_characters(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test getting setting with underscore in key."""
        setting = Setting(
            key="some_complex_key_name",
            value="value",
            updated_at=datetime.now(UTC),
        )
        mock_settings_repo.get.return_value = setting

        response = await client.get("/api/v1/settings/some_complex_key_name")

        assert response.status_code == 200


class TestUpdateSetting:
    """Tests for PUT /api/v1/settings/{key}."""

    @pytest.mark.asyncio
    async def test_update_setting_success(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test updating setting."""
        updated_setting = Setting(
            key="telegram_chat_id",
            value=987654321,
            updated_at=datetime.now(UTC),
        )
        mock_settings_repo.set.return_value = updated_setting

        response = await client.put(
            "/api/v1/settings/telegram_chat_id",
            json={"value": 987654321},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "telegram_chat_id"
        assert data["value"] == 987654321
        mock_settings_repo.set.assert_called_once_with("telegram_chat_id", 987654321)

    @pytest.mark.asyncio
    async def test_update_setting_creates_new(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test creating new setting via PUT."""
        new_setting = Setting(
            key="new_setting",
            value="new_value",
            updated_at=datetime.now(UTC),
        )
        mock_settings_repo.set.return_value = new_setting

        response = await client.put(
            "/api/v1/settings/new_setting",
            json={"value": "new_value"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "new_setting"
        assert data["value"] == "new_value"

    @pytest.mark.asyncio
    async def test_update_setting_with_complex_value(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test updating setting with complex JSON value."""
        complex_value = {
            "nested": {
                "key": "value",
                "list": [1, 2, 3],
            },
            "enabled": True,
        }
        new_setting = Setting(
            key="complex_setting",
            value=complex_value,
            updated_at=datetime.now(UTC),
        )
        mock_settings_repo.set.return_value = new_setting

        response = await client.put(
            "/api/v1/settings/complex_setting",
            json={"value": complex_value},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["value"] == complex_value

    @pytest.mark.asyncio
    async def test_update_setting_with_null_value(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test updating setting with null value."""
        new_setting = Setting(
            key="nullable_setting",
            value=None,
            updated_at=datetime.now(UTC),
        )
        mock_settings_repo.set.return_value = new_setting

        response = await client.put(
            "/api/v1/settings/nullable_setting",
            json={"value": None},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["value"] is None


class TestDeleteSetting:
    """Tests for DELETE /api/v1/settings/{key}."""

    @pytest.mark.asyncio
    async def test_delete_setting_success(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test deleting existing setting."""
        mock_settings_repo.delete.return_value = True

        response = await client.delete("/api/v1/settings/telegram_chat_id")

        assert response.status_code == 204
        mock_settings_repo.delete.assert_called_once_with("telegram_chat_id")

    @pytest.mark.asyncio
    async def test_delete_setting_not_found(
        self,
        client: AsyncClient,
        mock_settings_repo: AsyncMock,
    ) -> None:
        """Test deleting non-existent setting."""
        mock_settings_repo.delete.return_value = False

        response = await client.delete("/api/v1/settings/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
