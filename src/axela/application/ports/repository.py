"""Repository protocol definitions."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from axela.domain.enums import SourceType
from axela.domain.models import (
    CollectorError,
    Digest,
    DigestItem,
    Project,
    Schedule,
    Setting,
    Source,
)


class ProjectRepository(Protocol):
    """Protocol for project repository."""

    async def create(self, name: str, color: str | None = None) -> Project:
        """Create a new project."""
        ...

    async def get_by_id(self, project_id: UUID) -> Project | None:
        """Get project by ID."""
        ...

    async def get_by_name(self, name: str) -> Project | None:
        """Get project by name."""
        ...

    async def get_all(self) -> list[Project]:
        """Get all projects."""
        ...

    async def update(
        self,
        project_id: UUID,
        name: str | None = None,
        color: str | None = None,
    ) -> Project | None:
        """Update a project."""
        ...

    async def delete(self, project_id: UUID) -> bool:
        """Delete a project."""
        ...


class SourceRepository(Protocol):
    """Protocol for source repository."""

    async def create(
        self,
        project_id: UUID,
        source_type: SourceType,
        name: str,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> Source:
        """Create a new source."""
        ...

    async def get_by_id(self, source_id: UUID) -> Source | None:
        """Get source by ID."""
        ...

    async def get_by_project(self, project_id: UUID) -> list[Source]:
        """Get all sources for a project."""
        ...

    async def get_active(self) -> list[Source]:
        """Get all active sources."""
        ...

    async def get_by_type(self, source_type: SourceType) -> list[Source]:
        """Get all sources of a specific type."""
        ...

    async def update(
        self,
        source_id: UUID,
        name: str | None = None,
        credentials: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        is_active: bool | None = None,
    ) -> Source | None:
        """Update a source."""
        ...

    async def update_last_synced(
        self,
        source_id: UUID,
        last_synced_at: datetime,
    ) -> None:
        """Update the last synced timestamp."""
        ...

    async def delete(self, source_id: UUID) -> bool:
        """Delete a source."""
        ...


class ItemRepository(Protocol):
    """Protocol for item repository."""

    async def upsert(self, item: DigestItem) -> UUID:
        """Insert or update an item. Returns the item ID."""
        ...

    async def upsert_many(self, items: list[DigestItem]) -> list[UUID]:
        """Insert or update multiple items. Returns item IDs."""
        ...

    async def get_by_id(self, item_id: UUID) -> DigestItem | None:
        """Get item by ID."""
        ...

    async def get_by_external_id(
        self,
        source_id: UUID,
        external_id: str,
    ) -> DigestItem | None:
        """Get item by source and external ID."""
        ...

    async def get_changed_since_last_digest(
        self,
        source_id: UUID,
    ) -> list[tuple[DigestItem, UUID]]:
        """Get items that changed since last shown in a digest.

        Returns tuples of (item, item_id) for items whose content_hash
        differs from the last digest_items.content_hash_at_send.
        """
        ...

    async def get_new_items(
        self,
        source_id: UUID,
        since: datetime,
    ) -> list[tuple[DigestItem, UUID]]:
        """Get items fetched since a given time.

        Returns tuples of (item, item_id).
        """
        ...


class DigestRepository(Protocol):
    """Protocol for digest repository."""

    async def create(
        self,
        digest_type: str,
        scheduled_at: datetime | None = None,
    ) -> Digest:
        """Create a new digest."""
        ...

    async def get_by_id(self, digest_id: UUID) -> Digest | None:
        """Get digest by ID."""
        ...

    async def get_latest(self, digest_type: str | None = None) -> Digest | None:
        """Get the most recent digest, optionally filtered by type."""
        ...

    async def get_history(
        self,
        limit: int = 10,
        offset: int = 0,
        digest_type: str | None = None,
    ) -> list[Digest]:
        """Get digest history."""
        ...

    async def update_status(
        self,
        digest_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Update digest status."""
        ...

    async def mark_sent(
        self,
        digest_id: UUID,
        telegram_message_id: int,
        content: str,
        item_count: int,
    ) -> None:
        """Mark digest as sent."""
        ...

    async def add_items(
        self,
        digest_id: UUID,
        items: list[tuple[UUID, str]],  # (item_id, content_hash)
    ) -> None:
        """Add items to a digest."""
        ...


class ScheduleRepository(Protocol):
    """Protocol for schedule repository."""

    async def create(
        self,
        name: str,
        digest_type: str,
        cron_expression: str,
        timezone: str = "Europe/Lisbon",
        project_ids: list[UUID] | None = None,
    ) -> Schedule:
        """Create a new schedule."""
        ...

    async def get_by_id(self, schedule_id: UUID) -> Schedule | None:
        """Get schedule by ID."""
        ...

    async def get_active(self) -> list[Schedule]:
        """Get all active schedules."""
        ...

    async def update(
        self,
        schedule_id: UUID,
        name: str | None = None,
        cron_expression: str | None = None,
        timezone: str | None = None,
        is_active: bool | None = None,
        project_ids: list[UUID] | None = None,
    ) -> Schedule | None:
        """Update a schedule."""
        ...

    async def delete(self, schedule_id: UUID) -> bool:
        """Delete a schedule."""
        ...


class CollectorErrorRepository(Protocol):
    """Protocol for collector error repository."""

    async def create(
        self,
        source_id: UUID,
        error_type: str,
        error_message: str,
    ) -> CollectorError:
        """Create a new error record."""
        ...

    async def get_unresolved(self, source_id: UUID | None = None) -> list[CollectorError]:
        """Get unresolved errors, optionally filtered by source."""
        ...

    async def mark_resolved(self, error_id: UUID) -> None:
        """Mark an error as resolved."""
        ...

    async def mark_all_resolved(self, source_id: UUID) -> None:
        """Mark all errors for a source as resolved."""
        ...


class SettingsRepository(Protocol):
    """Protocol for settings repository."""

    async def get(self, key: str) -> Setting | None:
        """Get a setting by key."""
        ...

    async def get_all(self) -> list[Setting]:
        """Get all settings."""
        ...

    async def set(self, key: str, value: Any) -> Setting:
        """Set a setting value (insert or update)."""
        ...

    async def delete(self, key: str) -> bool:
        """Delete a setting."""
        ...
