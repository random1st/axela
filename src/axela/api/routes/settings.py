"""Settings API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from axela.api.deps import SettingsRepoDep

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingResponse(BaseModel):
    """Response model for a setting."""

    key: str
    value: Any
    updated_at: str | None

    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    """Request model for updating a setting."""

    value: Any


@router.get("")
async def list_settings(repo: SettingsRepoDep) -> list[SettingResponse]:
    """List all settings."""
    settings = await repo.get_all()
    return [
        SettingResponse(
            key=s.key,
            value=s.value,
            updated_at=s.updated_at.isoformat() if s.updated_at else None,
        )
        for s in settings
    ]


@router.get("/{key}")
async def get_setting(
    key: str,
    repo: SettingsRepoDep,
) -> SettingResponse:
    """Get a setting by key."""
    setting = await repo.get(key)
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )
    return SettingResponse(
        key=setting.key,
        value=setting.value,
        updated_at=setting.updated_at.isoformat() if setting.updated_at else None,
    )


@router.put("/{key}")
async def update_setting(
    key: str,
    data: SettingUpdate,
    repo: SettingsRepoDep,
) -> SettingResponse:
    """Update a setting value (creates if not exists)."""
    setting = await repo.set(key, data.value)
    return SettingResponse(
        key=setting.key,
        value=setting.value,
        updated_at=setting.updated_at.isoformat() if setting.updated_at else None,
    )


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    key: str,
    repo: SettingsRepoDep,
) -> None:
    """Delete a setting."""
    deleted = await repo.delete(key)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )
