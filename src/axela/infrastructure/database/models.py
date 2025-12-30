"""SQLAlchemy ORM models."""

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    type_annotation_map: ClassVar[dict[type, Any]] = {
        dict[str, Any]: JSONB,
        list[UUID]: ARRAY(PG_UUID(as_uuid=True)),
    }


class ProjectModel(Base):
    """Projects table - groups sources by project."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str | None] = mapped_column(String(7))  # hex color
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    sources: Mapped[list["SourceModel"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """Return string representation of the project."""
        return f"<Project {self.name}>"


class SourceModel(Base):
    """Sources table - data source accounts."""

    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    credentials: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    project: Mapped["ProjectModel"] = relationship(back_populates="sources")
    items: Mapped[list["ItemModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    errors: Mapped[list["CollectorErrorModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """Return string representation of the source."""
        return f"<Source {self.name} ({self.source_type})>"


class ItemModel(Base):
    """Items table - raw items from collectors."""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_items_source_external"),
        Index("idx_items_source_external", "source_id", "external_id"),
        Index("idx_items_fetched_at", "fetched_at"),
        Index("idx_items_content_hash", "content_hash"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    external_url: Mapped[str | None] = mapped_column(Text)
    external_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    source: Mapped["SourceModel"] = relationship(back_populates="items")
    digest_items: Mapped[list["DigestItemModel"]] = relationship(back_populates="item", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """Return string representation of the item."""
        return f"<Item {self.external_id} ({self.item_type})>"


class DigestModel(Base):
    """Digests table - digest history."""

    __tablename__ = "digests"
    __table_args__ = (Index("idx_digests_sent_at", "sent_at"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    digest_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str | None] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    digest_items: Mapped[list["DigestItemModel"]] = relationship(back_populates="digest", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """Return string representation of the digest."""
        return f"<Digest {self.digest_type} ({self.status})>"


class DigestItemModel(Base):
    """DigestItems table - tracks what items were shown in digests."""

    __tablename__ = "digest_items"
    __table_args__ = (UniqueConstraint("digest_id", "item_id", name="uq_digest_items"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    digest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("digests.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    content_hash_at_send: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    digest: Mapped["DigestModel"] = relationship(back_populates="digest_items")
    item: Mapped["ItemModel"] = relationship(back_populates="digest_items")

    def __repr__(self) -> str:
        """Return string representation of the digest item."""
        return f"<DigestItem digest={self.digest_id} item={self.item_id}>"


class ScheduleModel(Base):
    """Schedules table - user-defined schedules."""

    __tablename__ = "schedules"
    __table_args__ = (Index("idx_schedules_active", "is_active", postgresql_where="is_active = true"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    digest_type: Mapped[str] = mapped_column(String(20), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Lisbon")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    project_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return string representation of the schedule."""
        return f"<Schedule {self.name} ({self.cron_expression})>"


class CollectorErrorModel(Base):
    """CollectorErrors table - collector errors for alerting."""

    __tablename__ = "collector_errors"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    source: Mapped["SourceModel"] = relationship(back_populates="errors")

    def __repr__(self) -> str:
        """Return string representation of the collector error."""
        return f"<CollectorError {self.error_type} (resolved={self.resolved})>"


class SettingModel(Base):
    """Settings table - key-value store for app configuration."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return string representation of the setting."""
        return f"<Setting {self.key}>"
