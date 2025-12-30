"""Health check endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from axela import __version__
from axela.api.deps import get_scheduler
from axela.infrastructure.database import get_async_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


class ReadyResponse(BaseModel):
    """Readiness check response."""

    status: str
    database: str
    scheduler: str


@router.get("/health")
async def health_check() -> HealthResponse:
    """Return basic health status."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/health/ready")
async def readiness_check(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ReadyResponse:
    """Readiness check - verifies database and scheduler are ready."""
    # Check database
    try:
        await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    # Check scheduler
    scheduler = get_scheduler()
    if scheduler is None:
        scheduler_status = "not configured"
    elif scheduler.is_running:
        scheduler_status = "ok"
    else:
        scheduler_status = "stopped"

    overall_status = "ok" if db_status == "ok" and scheduler_status == "ok" else "degraded"

    return ReadyResponse(
        status=overall_status,
        database=db_status,
        scheduler=scheduler_status,
    )
