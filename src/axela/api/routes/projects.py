"""Project CRUD API endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from axela.api.deps import ProjectRepoDep

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    """Request model for creating a project."""

    name: str = Field(..., min_length=1, max_length=100)
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ProjectUpdate(BaseModel):
    """Request model for updating a project."""

    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ProjectResponse(BaseModel):
    """Response model for a project."""

    id: UUID
    name: str
    color: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    data: ProjectCreate,
    repo: ProjectRepoDep,
) -> ProjectResponse:
    """Create a new project."""
    # Check if name already exists
    existing = await repo.get_by_name(data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with name '{data.name}' already exists",
        )

    project = await repo.create(name=data.name, color=data.color)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        color=project.color,
        created_at=project.created_at.isoformat() if project.created_at else "",
    )


@router.get("")
async def list_projects(repo: ProjectRepoDep) -> list[ProjectResponse]:
    """List all projects."""
    projects = await repo.get_all()
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            color=p.color,
            created_at=p.created_at.isoformat() if p.created_at else "",
        )
        for p in projects
    ]


@router.get("/{project_id}")
async def get_project(
    project_id: UUID,
    repo: ProjectRepoDep,
) -> ProjectResponse:
    """Get a project by ID."""
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return ProjectResponse(
        id=project.id,
        name=project.name,
        color=project.color,
        created_at=project.created_at.isoformat() if project.created_at else "",
    )


@router.patch("/{project_id}")
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    repo: ProjectRepoDep,
) -> ProjectResponse:
    """Update a project."""
    # Check if new name conflicts
    if data.name:
        existing = await repo.get_by_name(data.name)
        if existing and existing.id != project_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with name '{data.name}' already exists",
            )

    project = await repo.update(
        project_id=project_id,
        name=data.name,
        color=data.color,
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return ProjectResponse(
        id=project.id,
        name=project.name,
        color=project.color,
        created_at=project.created_at.isoformat() if project.created_at else "",
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    repo: ProjectRepoDep,
) -> None:
    """Delete a project."""
    deleted = await repo.delete(project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
