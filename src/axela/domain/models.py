"""Domain models - pure Python dataclasses."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from .enums import DigestStatus, DigestType, ItemType, SourceType


@dataclass(frozen=True, slots=True)
class Project:
    """A project grouping multiple data sources."""

    id: UUID
    name: str
    color: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Source:
    """A data source (e.g., a Jira account, Gmail account)."""

    id: UUID
    project_id: UUID
    source_type: SourceType
    name: str
    credentials: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    last_synced_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DigestItem:
    """A single item to include in a digest."""

    source_id: UUID
    external_id: str
    item_type: ItemType
    title: str | None
    content: dict[str, Any]
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    external_url: str | None = None
    external_created_at: datetime | None = None
    external_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Schedule:
    """A digest schedule."""

    id: UUID
    name: str
    digest_type: DigestType
    cron_expression: str
    timezone: str = "Europe/Lisbon"
    is_active: bool = True
    project_ids: list[UUID] = field(default_factory=list)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Digest:
    """A generated digest."""

    id: UUID
    digest_type: DigestType
    status: DigestStatus = DigestStatus.PENDING
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    telegram_message_id: int | None = None
    content: str | None = None
    item_count: int = 0
    error_message: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CollectorError:
    """An error from a collector."""

    id: UUID
    source_id: UUID
    error_type: str
    error_message: str
    resolved: bool = False
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Setting:
    """A configuration setting (key-value)."""

    key: str
    value: Any
    updated_at: datetime | None = None
