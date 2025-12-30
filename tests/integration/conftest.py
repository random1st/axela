"""Fixtures for integration tests with SQLite in-memory database."""

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    event,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UUIDString(TypeDecorator[UUID]):
    """Platform-independent UUID type that uses String storage for SQLite."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value: UUID | None, dialect: Any) -> str | None:
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value: str | None, dialect: Any) -> UUID | None:
        if value is not None:
            return UUID(value)
        return value


class JSONList(TypeDecorator[list[UUID]]):
    """Store list of UUIDs as JSON string for SQLite compatibility."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: list[UUID] | None, dialect: Any) -> str | None:
        if value is not None:
            return json.dumps([str(u) for u in value])
        return None

    def process_result_value(self, value: str | None, dialect: Any) -> list[UUID] | None:
        if value is not None:
            return [UUID(u) for u in json.loads(value)]
        return []


class SQLiteBase(DeclarativeBase):
    """Base class for SQLite ORM models with compatible types."""

    type_annotation_map: ClassVar[dict[type, Any]] = {
        dict[str, Any]: JSON,
        list[UUID]: JSONList,
        UUID: UUIDString,
    }


# SQLite-compatible models (using SQLite prefix to avoid pytest collection)


class SQLiteProjectModel(SQLiteBase):
    """Projects table for SQLite testing."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(UUIDString, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str | None] = mapped_column(String(7))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    sources: Mapped[list["SQLiteSourceModel"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class SQLiteSourceModel(SQLiteBase):
    """Sources table for SQLite testing."""

    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(UUIDString, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    credentials: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    project: Mapped["SQLiteProjectModel"] = relationship(back_populates="sources")
    items: Mapped[list["SQLiteItemModel"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    errors: Mapped[list["SQLiteCollectorErrorModel"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class SQLiteItemModel(SQLiteBase):
    """Items table for SQLite testing."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_items_source_external"),)

    id: Mapped[UUID] = mapped_column(UUIDString, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(UUIDString, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    external_url: Mapped[str | None] = mapped_column(Text)
    external_created_at: Mapped[datetime | None] = mapped_column(DateTime)
    external_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    source: Mapped["SQLiteSourceModel"] = relationship(back_populates="items")
    digest_items: Mapped[list["SQLiteDigestItemModel"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class SQLiteDigestModel(SQLiteBase):
    """Digests table for SQLite testing."""

    __tablename__ = "digests"

    id: Mapped[UUID] = mapped_column(UUIDString, primary_key=True, default=uuid4)
    digest_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str | None] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    digest_items: Mapped[list["SQLiteDigestItemModel"]] = relationship(
        back_populates="digest", cascade="all, delete-orphan"
    )


class SQLiteDigestItemModel(SQLiteBase):
    """DigestItems table for SQLite testing."""

    __tablename__ = "digest_items"
    __table_args__ = (UniqueConstraint("digest_id", "item_id", name="uq_digest_items"),)

    id: Mapped[UUID] = mapped_column(UUIDString, primary_key=True, default=uuid4)
    digest_id: Mapped[UUID] = mapped_column(UUIDString, ForeignKey("digests.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[UUID] = mapped_column(UUIDString, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    content_hash_at_send: Mapped[str] = mapped_column(String(64), nullable=False)

    digest: Mapped["SQLiteDigestModel"] = relationship(back_populates="digest_items")
    item: Mapped["SQLiteItemModel"] = relationship(back_populates="digest_items")


class SQLiteScheduleModel(SQLiteBase):
    """Schedules table for SQLite testing."""

    __tablename__ = "schedules"

    id: Mapped[UUID] = mapped_column(UUIDString, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    digest_type: Mapped[str] = mapped_column(String(20), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Lisbon")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    project_ids: Mapped[list[UUID]] = mapped_column(JSONList, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class SQLiteCollectorErrorModel(SQLiteBase):
    """CollectorErrors table for SQLite testing."""

    __tablename__ = "collector_errors"

    id: Mapped[UUID] = mapped_column(UUIDString, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(UUIDString, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    source: Mapped["SQLiteSourceModel"] = relationship(back_populates="errors")


class SQLiteSettingModel(SQLiteBase):
    """Settings table for SQLite testing."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


@pytest.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine]:
    """Create SQLite in-memory async engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Enable foreign keys for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(SQLiteBase.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def sqlite_session(sqlite_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Create SQLite async session."""
    session_factory = async_sessionmaker(
        sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()
