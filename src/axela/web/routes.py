"""Web frontend routes using Jinja2 templates and HTMX."""

import json
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from axela.api.deps import (
    get_project_repository,
    get_schedule_repository,
    get_session,
    get_settings_repository,
    get_source_repository,
    get_telegram_bot,
)
from axela.api.middleware.auth import verify_credentials
from axela.application.ports.repository import (
    ProjectRepository,
    ScheduleRepository,
    SettingsRepository,
    SourceRepository,
)
from axela.domain.enums import SourceType
from axela.infrastructure.collectors.base import CollectorRegistry

# Setup templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Create routers with basic auth
router = APIRouter(prefix="", tags=["web"], dependencies=[Depends(verify_credentials)])
api_router = APIRouter(prefix="/api", tags=["web-api"], dependencies=[Depends(verify_credentials)])


# ============================================================================
# Page Routes
# ============================================================================


@router.get("/", response_class=HTMLResponse, name="dashboard")
async def dashboard(
    request: Request,
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    source_repo: Annotated[SourceRepository, Depends(get_source_repository)],
    schedule_repo: Annotated[ScheduleRepository, Depends(get_schedule_repository)],
) -> HTMLResponse:
    """Render dashboard page with overview statistics."""
    projects = await project_repo.get_all()
    sources = await source_repo.get_active()
    schedules = await schedule_repo.get_active()

    stats = {
        "projects": len(projects),
        "sources": len(sources),
        "schedules": len(schedules),
        "digests_sent": 0,  # Placeholder for future implementation
    }

    # Create project dicts with sources_count (Project is frozen dataclass)
    recent_projects = []
    for project in projects[:5]:
        project_dict = {
            "id": project.id,
            "name": project.name,
            "color": project.color,
            "sources_count": len([s for s in sources if s.project_id == project.id]),
        }
        recent_projects.append(project_dict)

    return templates.TemplateResponse(
        request=request,
        name="pages/dashboard.html",
        context={
            "active_page": "dashboard",
            "stats": stats,
            "recent_projects": recent_projects,
        },
    )


@router.get("/projects", response_class=HTMLResponse, name="projects_list")
async def projects_list(
    request: Request,
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> HTMLResponse:
    """Render projects listing page."""
    projects = await project_repo.get_all()

    return templates.TemplateResponse(
        request=request,
        name="pages/projects.html",
        context={
            "active_page": "projects",
            "projects": projects,
        },
    )


@router.get("/sources", response_class=HTMLResponse, name="sources_list")
async def sources_list(
    request: Request,
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    source_repo: Annotated[SourceRepository, Depends(get_source_repository)],
    project: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Render sources listing page."""
    projects = await project_repo.get_all()

    if project:
        sources = await source_repo.get_by_project(UUID(project))
    else:
        sources = await source_repo.get_active()

    # Add project name to each source
    project_map = {p.id: p.name for p in projects}
    for source in sources:
        source.project_name = project_map.get(source.project_id, "Unknown")  # type: ignore[attr-defined]

    return templates.TemplateResponse(
        request=request,
        name="pages/sources.html",
        context={
            "active_page": "sources",
            "projects": projects,
            "sources": sources,
            "selected_project": project,
        },
    )


@router.get("/schedules", response_class=HTMLResponse, name="schedules_list")
async def schedules_list(
    request: Request,
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    schedule_repo: Annotated[ScheduleRepository, Depends(get_schedule_repository)],
) -> HTMLResponse:
    """Render schedules listing page."""
    projects = await project_repo.get_all()
    schedules = await schedule_repo.get_active()

    return templates.TemplateResponse(
        request=request,
        name="pages/schedules.html",
        context={
            "active_page": "schedules",
            "projects": projects,
            "schedules": schedules,
        },
    )


@router.get("/settings", response_class=HTMLResponse, name="settings_page")
async def settings_page(
    request: Request,
    settings_repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
) -> HTMLResponse:
    """Render settings page."""
    all_settings = await settings_repo.get_all()

    # Convert to dict for easy access
    settings_dict = {s.key: s.value for s in all_settings}

    return templates.TemplateResponse(
        request=request,
        name="pages/settings.html",
        context={
            "active_page": "settings",
            "settings": settings_dict,
            "all_settings": all_settings,
            "version": "0.1.0",
        },
    )


# ============================================================================
# API Routes for HTMX
# ============================================================================


@api_router.get("/status", response_class=HTMLResponse)
async def get_status(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HTMLResponse:
    """Return system status for dashboard."""
    # Check database
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    # Check scheduler and telegram (simplified check)
    bot = get_telegram_bot()

    status = {
        "database": db_ok,
        "scheduler": True,  # Assume OK if app is running
        "telegram": bot is not None and bot.is_running,
    }

    return templates.TemplateResponse(
        request=request,
        name="components/status.html",
        context={"status": status},
    )


# Projects API


@api_router.post("/projects", response_class=HTMLResponse)
async def create_project(
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    name: Annotated[str, Form()],
    color: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """Create a new project via HTMX."""
    try:
        await project_repo.create(name=name, color=color if color else None)
        return HTMLResponse(content="")
    except IntegrityError:
        return HTMLResponse(
            content="Проект с таким именем уже существует",
            status_code=400,
        )


@api_router.put("/projects/{project_id}", response_class=HTMLResponse)
async def update_project(
    project_id: UUID,
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    name: Annotated[str, Form()],
    color: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """Update a project via HTMX."""
    updated = await project_repo.update(
        project_id=project_id,
        name=name,
        color=color if color else None,
    )

    if updated:
        return HTMLResponse(content="")

    return HTMLResponse(content="", status_code=404)


@api_router.delete("/projects/{project_id}", response_class=HTMLResponse)
async def delete_project(
    project_id: UUID,
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> HTMLResponse:
    """Delete a project via HTMX."""
    await project_repo.delete(project_id)
    return HTMLResponse(content="")


# Sources API


def _parse_credentials(form_data: dict[str, Any]) -> dict[str, Any]:
    """Parse credentials from form data."""
    credentials: dict[str, Any] = {}
    for key, value in form_data.items():
        if key.startswith("credentials.") and value:
            cred_key = key.replace("credentials.", "")
            # Try to parse JSON for complex values
            if cred_key == "credentials_json":
                try:
                    credentials[cred_key] = json.loads(value)
                except json.JSONDecodeError:
                    credentials[cred_key] = value
            else:
                credentials[cred_key] = value
    return credentials


def _parse_config(form_data: dict[str, Any]) -> dict[str, Any]:
    """Parse config from form data."""
    config: dict[str, Any] = {}
    for key, value in form_data.items():
        if key.startswith("config.") and value:
            config_key = key.replace("config.", "")
            config[config_key] = value
    return config


@api_router.post("/sources", response_class=HTMLResponse)
async def create_source(
    request: Request,
    source_repo: Annotated[SourceRepository, Depends(get_source_repository)],
) -> HTMLResponse:
    """Create a new source via HTMX."""
    form_data = await request.form()
    form_dict = dict(form_data)

    project_id = UUID(str(form_dict["project_id"]))
    source_type_str = str(form_dict["source_type"])
    name = str(form_dict["name"])

    credentials = _parse_credentials(form_dict)
    config = _parse_config(form_dict)

    # Convert string to SourceType enum
    source_type = SourceType(source_type_str)

    await source_repo.create(
        project_id=project_id,
        source_type=source_type,
        name=name,
        credentials=credentials,
        config=config if config else None,
    )

    return HTMLResponse(content="")


@api_router.put("/sources/{source_id}", response_class=HTMLResponse)
async def update_source(
    source_id: UUID,
    source_repo: Annotated[SourceRepository, Depends(get_source_repository)],
    name: Annotated[str, Form()],
    is_active: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    """Update a source via HTMX."""
    updated = await source_repo.update(
        source_id=source_id,
        name=name,
        is_active=is_active,
    )

    if updated:
        return HTMLResponse(content="")

    return HTMLResponse(content="", status_code=404)


@api_router.delete("/sources/{source_id}", response_class=HTMLResponse)
async def delete_source(
    source_id: UUID,
    source_repo: Annotated[SourceRepository, Depends(get_source_repository)],
) -> HTMLResponse:
    """Delete a source via HTMX."""
    await source_repo.delete(source_id)
    return HTMLResponse(content="")


@api_router.post("/sources/{source_id}/test")
async def test_source_credentials(
    source_id: UUID,
    source_repo: Annotated[SourceRepository, Depends(get_source_repository)],
) -> dict[str, Any]:
    """Test source credentials validity."""
    source = await source_repo.get_by_id(source_id)
    if not source:
        return {"valid": False, "error": "Source not found"}

    collector_class = CollectorRegistry.get(source.source_type)
    if not collector_class:
        return {"valid": False, "error": "No collector available"}

    try:
        collector = collector_class()
        is_valid = await collector.validate_credentials(source.credentials)
        if is_valid:
            return {"valid": True, "error": None}
        return {"valid": False, "error": "Invalid credentials"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


# Schedules API


@api_router.post("/schedules", response_class=HTMLResponse)
async def create_schedule(
    request: Request,
    schedule_repo: Annotated[ScheduleRepository, Depends(get_schedule_repository)],
) -> HTMLResponse:
    """Create a new schedule via HTMX."""
    form_data = await request.form()
    form_dict = dict(form_data)

    # Handle project_ids as list
    project_ids = form_data.getlist("project_ids")
    project_ids_list = [UUID(str(pid)) for pid in project_ids] if project_ids else None

    await schedule_repo.create(
        name=str(form_dict["name"]),
        digest_type=str(form_dict["digest_type"]),
        cron_expression=str(form_dict["cron_expression"]),
        timezone=str(form_dict.get("timezone", "UTC")),
        project_ids=project_ids_list,
    )

    return HTMLResponse(content="")


@api_router.put("/schedules/{schedule_id}", response_class=HTMLResponse)
async def update_schedule(
    schedule_id: UUID,
    schedule_repo: Annotated[ScheduleRepository, Depends(get_schedule_repository)],
    name: Annotated[str, Form()],
    digest_type: Annotated[str, Form()],
    cron_expression: Annotated[str, Form()],
    timezone: Annotated[str, Form()] = "UTC",
    is_active: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    """Update a schedule via HTMX."""
    updated = await schedule_repo.update(
        schedule_id=schedule_id,
        name=name,
        cron_expression=cron_expression,
        timezone=timezone,
        is_active=is_active,
    )

    if updated:
        return HTMLResponse(content="")

    return HTMLResponse(content="", status_code=404)


@api_router.delete("/schedules/{schedule_id}", response_class=HTMLResponse)
async def delete_schedule(
    schedule_id: UUID,
    schedule_repo: Annotated[ScheduleRepository, Depends(get_schedule_repository)],
) -> HTMLResponse:
    """Delete a schedule via HTMX."""
    await schedule_repo.delete(schedule_id)
    return HTMLResponse(content="")


# Settings API


@api_router.post("/settings", response_class=HTMLResponse)
async def create_setting(
    settings_repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
    key: Annotated[str, Form()],
    value: Annotated[str, Form()],
) -> HTMLResponse:
    """Create a new setting via HTMX."""
    await settings_repo.set(key, value)

    return HTMLResponse(
        content=f"""
        <div id="setting-{key.replace(".", "-")}" class="row small-padding border-bottom">
            <div class="max">
                <p class="bold">{key}</p>
                <p class="secondary-text small-text">{value[:50]}{"..." if len(value) > 50 else ""}</p>
            </div>
            <button class="circle transparent small" onclick="editSetting('{key}', '{value}')">
                <i>edit</i>
            </button>
            <button class="circle transparent small"
                    hx-delete="/web/api/settings/{key}"
                    hx-target="#setting-{key.replace(".", "-")}"
                    hx-swap="outerHTML"
                    hx-confirm="Delete setting '{key}'?">
                <i>delete</i>
            </button>
        </div>
        """
    )


@api_router.put("/settings/{key}", response_class=HTMLResponse)
async def update_setting(
    key: str,
    settings_repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
    value: Annotated[str, Form()],
) -> HTMLResponse:
    """Update a setting via HTMX."""
    await settings_repo.set(key, value)
    return HTMLResponse(content="")


@api_router.delete("/settings/{key}", response_class=HTMLResponse)
async def delete_setting(
    key: str,
    settings_repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
) -> HTMLResponse:
    """Delete a setting via HTMX."""
    await settings_repo.delete(key)
    return HTMLResponse(content="")


@api_router.post("/settings/batch", response_class=HTMLResponse)
async def batch_update_settings(
    request: Request,
    settings_repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
) -> HTMLResponse:
    """Update multiple settings at once via HTMX."""
    form_data = await request.form()

    for key, value in form_data.items():
        if value:  # Only save non-empty values
            await settings_repo.set(key, str(value))

    return HTMLResponse(content="")
