"""Domain events for the message bus."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """Base class for all domain events."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True, kw_only=True)
class DigestScheduled(Event):
    """Event emitted when a digest is scheduled to be generated."""

    schedule_id: UUID
    digest_type: str
    project_ids: list[UUID] = field(default_factory=list)


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionStarted(Event):
    """Event emitted when collection starts for a source."""

    source_id: UUID
    digest_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionCompleted(Event):
    """Event emitted when collection completes for a source."""

    source_id: UUID
    digest_id: UUID
    items_count: int
    new_items_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectorFailed(Event):
    """Event emitted when a collector fails."""

    source_id: UUID
    error_type: str
    error_message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DigestReady(Event):
    """Event emitted when a digest is ready to be sent."""

    digest_id: UUID
    content: str
    item_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DigestSent(Event):
    """Event emitted when a digest is sent successfully."""

    digest_id: UUID
    telegram_message_id: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DigestFailed(Event):
    """Event emitted when sending a digest fails."""

    digest_id: UUID
    error_message: str
