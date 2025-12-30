"""Source CRUD API endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from axela.api.deps import ProjectRepoDep, SourceRepoDep
from axela.domain.enums import SourceType
from axela.domain.models import Source
from axela.infrastructure.collectors import CollectorRegistry

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreate(BaseModel):
    """Request model for creating a source."""

    project_id: UUID
    source_type: SourceType
    name: str = Field(..., min_length=1, max_length=100)
    credentials: dict[str, Any]
    config: dict[str, Any] = Field(default_factory=dict)


class SourceUpdate(BaseModel):
    """Request model for updating a source."""

    name: str | None = Field(None, min_length=1, max_length=100)
    credentials: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class SourceResponse(BaseModel):
    """Response model for a source."""

    id: UUID
    project_id: UUID
    source_type: SourceType
    name: str
    config: dict[str, Any]
    is_active: bool
    last_synced_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


class SourceTestResult(BaseModel):
    """Response model for credential test."""

    valid: bool
    message: str


def _source_to_response(source: Source) -> SourceResponse:
    """Convert domain Source to SourceResponse."""
    return SourceResponse(
        id=source.id,
        project_id=source.project_id,
        source_type=source.source_type,
        name=source.name,
        config=source.config,
        is_active=source.is_active,
        last_synced_at=source.last_synced_at.isoformat() if source.last_synced_at else None,
        created_at=source.created_at.isoformat() if source.created_at else "",
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_source(
    data: SourceCreate,
    source_repo: SourceRepoDep,
    project_repo: ProjectRepoDep,
) -> SourceResponse:
    """Create a new source."""
    # Verify project exists
    project = await project_repo.get_by_id(data.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Verify collector exists for this source type
    collector_class = CollectorRegistry.get(data.source_type)
    if not collector_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No collector available for source type: {data.source_type}",
        )

    source = await source_repo.create(
        project_id=data.project_id,
        source_type=data.source_type,
        name=data.name,
        credentials=data.credentials,
        config=data.config,
    )

    return _source_to_response(source)


@router.get("")
async def list_sources(
    source_repo: SourceRepoDep,
    project_id: UUID | None = None,
    source_type: SourceType | None = None,
    *,
    active_only: bool = False,
) -> list[SourceResponse]:
    """List sources with optional filters."""
    if active_only:
        sources = await source_repo.get_active()
    elif project_id:
        sources = await source_repo.get_by_project(project_id)
    elif source_type:
        sources = await source_repo.get_by_type(source_type)
    else:
        # Get all sources - need to implement in repo
        sources = await source_repo.get_active()
        # For now, get all active sources

    return [_source_to_response(s) for s in sources]


@router.get("/{source_id}")
async def get_source(
    source_id: UUID,
    source_repo: SourceRepoDep,
) -> SourceResponse:
    """Get a source by ID."""
    source = await source_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )
    return _source_to_response(source)


@router.patch("/{source_id}")
async def update_source(
    source_id: UUID,
    data: SourceUpdate,
    source_repo: SourceRepoDep,
) -> SourceResponse:
    """Update a source."""
    source = await source_repo.update(
        source_id=source_id,
        name=data.name,
        credentials=data.credentials,
        config=data.config,
        is_active=data.is_active,
    )
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )
    return _source_to_response(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    source_repo: SourceRepoDep,
) -> None:
    """Delete a source."""
    deleted = await source_repo.delete(source_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )


@router.post("/{source_id}/test")
async def test_source_credentials(
    source_id: UUID,
    source_repo: SourceRepoDep,
) -> SourceTestResult:
    """Test source credentials."""
    source = await source_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    collector = CollectorRegistry.create(source.source_type)
    if not collector:
        return SourceTestResult(
            valid=False,
            message=f"No collector available for source type: {source.source_type}",
        )

    try:
        valid = await collector.validate_credentials(source.credentials)
        return SourceTestResult(
            valid=valid,
            message="Credentials are valid" if valid else "Invalid credentials",
        )
    except Exception as e:
        return SourceTestResult(valid=False, message=str(e))
    finally:
        await collector.close()
