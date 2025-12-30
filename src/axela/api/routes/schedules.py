"""Schedule CRUD API endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from axela.api.deps import ScheduleRepoDep
from axela.domain.enums import DigestType

router = APIRouter(prefix="/schedules", tags=["schedules"])


class ScheduleCreate(BaseModel):
    """Request model for creating a schedule."""

    name: str = Field(..., min_length=1, max_length=100)
    digest_type: DigestType
    cron_expression: str = Field(..., min_length=1, max_length=100)
    timezone: str = Field(default="Europe/Lisbon", max_length=50)
    project_ids: list[UUID] = Field(default_factory=list)


class ScheduleUpdate(BaseModel):
    """Request model for updating a schedule."""

    name: str | None = Field(None, min_length=1, max_length=100)
    cron_expression: str | None = Field(None, min_length=1, max_length=100)
    timezone: str | None = Field(None, max_length=50)
    is_active: bool | None = None
    project_ids: list[UUID] | None = None


class ScheduleResponse(BaseModel):
    """Response model for a schedule."""

    id: UUID
    name: str
    digest_type: str
    cron_expression: str
    timezone: str
    is_active: bool
    project_ids: list[UUID]
    created_at: str | None

    model_config = {"from_attributes": True}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    data: ScheduleCreate,
    repo: ScheduleRepoDep,
) -> ScheduleResponse:
    """Create a new schedule."""
    schedule = await repo.create(
        name=data.name,
        digest_type=data.digest_type.value,
        cron_expression=data.cron_expression,
        timezone=data.timezone,
        project_ids=data.project_ids,
    )
    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        digest_type=schedule.digest_type.value,
        cron_expression=schedule.cron_expression,
        timezone=schedule.timezone,
        is_active=schedule.is_active,
        project_ids=schedule.project_ids,
        created_at=schedule.created_at.isoformat() if schedule.created_at else None,
    )


@router.get("")
async def list_schedules(repo: ScheduleRepoDep) -> list[ScheduleResponse]:
    """List all active schedules."""
    schedules = await repo.get_active()
    return [
        ScheduleResponse(
            id=s.id,
            name=s.name,
            digest_type=s.digest_type.value,
            cron_expression=s.cron_expression,
            timezone=s.timezone,
            is_active=s.is_active,
            project_ids=s.project_ids,
            created_at=s.created_at.isoformat() if s.created_at else None,
        )
        for s in schedules
    ]


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: UUID,
    repo: ScheduleRepoDep,
) -> ScheduleResponse:
    """Get a schedule by ID."""
    schedule = await repo.get_by_id(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        digest_type=schedule.digest_type.value,
        cron_expression=schedule.cron_expression,
        timezone=schedule.timezone,
        is_active=schedule.is_active,
        project_ids=schedule.project_ids,
        created_at=schedule.created_at.isoformat() if schedule.created_at else None,
    )


@router.patch("/{schedule_id}")
async def update_schedule(
    schedule_id: UUID,
    data: ScheduleUpdate,
    repo: ScheduleRepoDep,
) -> ScheduleResponse:
    """Update a schedule."""
    schedule = await repo.update(
        schedule_id=schedule_id,
        name=data.name,
        cron_expression=data.cron_expression,
        timezone=data.timezone,
        is_active=data.is_active,
        project_ids=data.project_ids,
    )
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        digest_type=schedule.digest_type.value,
        cron_expression=schedule.cron_expression,
        timezone=schedule.timezone,
        is_active=schedule.is_active,
        project_ids=schedule.project_ids,
        created_at=schedule.created_at.isoformat() if schedule.created_at else None,
    )


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: UUID,
    repo: ScheduleRepoDep,
) -> None:
    """Delete a schedule."""
    deleted = await repo.delete(schedule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
