"""Repository implementations using SQLAlchemy."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from axela.domain.enums import DigestStatus, DigestType, ItemType, SourceType
from axela.domain.models import (
    CollectorError,
    Digest,
    DigestItem,
    Project,
    Schedule,
    Setting,
    Source,
)

from .models import (
    CollectorErrorModel,
    DigestItemModel,
    DigestModel,
    ItemModel,
    ProjectModel,
    ScheduleModel,
    SettingModel,
    SourceModel,
)


class ProjectRepositoryImpl:
    """SQLAlchemy implementation of ProjectRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self._session = session

    async def create(self, name: str, color: str | None = None) -> Project:
        """Create a new project."""
        model = ProjectModel(name=name, color=color)
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_id(self, project_id: UUID) -> Project | None:
        """Get project by ID."""
        result = await self._session.get(ProjectModel, project_id)
        return self._to_domain(result) if result else None

    async def get_by_name(self, name: str) -> Project | None:
        """Get project by name."""
        stmt = select(ProjectModel).where(ProjectModel.name == name)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_all(self) -> list[Project]:
        """Get all projects."""
        stmt = select(ProjectModel).order_by(ProjectModel.name)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def update(
        self,
        project_id: UUID,
        name: str | None = None,
        color: str | None = None,
    ) -> Project | None:
        """Update project fields."""
        model = await self._session.get(ProjectModel, project_id)
        if not model:
            return None
        if name is not None:
            model.name = name
        if color is not None:
            model.color = color
        await self._session.flush()
        return self._to_domain(model)

    async def delete(self, project_id: UUID) -> bool:
        """Delete project by ID."""
        model = await self._session.get(ProjectModel, project_id)
        if not model:
            return False
        await self._session.delete(model)
        return True

    @staticmethod
    def _to_domain(model: ProjectModel) -> Project:
        return Project(
            id=model.id,
            name=model.name,
            color=model.color,
            created_at=model.created_at,
        )


class SourceRepositoryImpl:
    """SQLAlchemy implementation of SourceRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self._session = session

    async def create(
        self,
        project_id: UUID,
        source_type: SourceType,
        name: str,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> Source:
        """Create a new source."""
        model = SourceModel(
            project_id=project_id,
            source_type=source_type.value,
            name=name,
            credentials=credentials,
            config=config or {},
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_id(self, source_id: UUID) -> Source | None:
        """Get source by ID."""
        result = await self._session.get(SourceModel, source_id)
        return self._to_domain(result) if result else None

    async def get_by_project(self, project_id: UUID) -> list[Source]:
        """Get all sources for a project."""
        stmt = select(SourceModel).where(SourceModel.project_id == project_id)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def get_active(self) -> list[Source]:
        """Get all active sources."""
        stmt = select(SourceModel).where(SourceModel.is_active == True)  # noqa: E712
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def get_by_type(self, source_type: SourceType) -> list[Source]:
        """Get all sources of a specific type."""
        stmt = select(SourceModel).where(SourceModel.source_type == source_type.value)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def update(
        self,
        source_id: UUID,
        name: str | None = None,
        credentials: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        is_active: bool | None = None,
    ) -> Source | None:
        """Update source fields."""
        model = await self._session.get(SourceModel, source_id)
        if not model:
            return None
        if name is not None:
            model.name = name
        if credentials is not None:
            model.credentials = credentials
        if config is not None:
            model.config = config
        if is_active is not None:
            model.is_active = is_active
        await self._session.flush()
        return self._to_domain(model)

    async def update_last_synced(
        self,
        source_id: UUID,
        last_synced_at: datetime,
    ) -> None:
        """Update source last synced timestamp."""
        stmt = update(SourceModel).where(SourceModel.id == source_id).values(last_synced_at=last_synced_at)
        await self._session.execute(stmt)

    async def delete(self, source_id: UUID) -> bool:
        """Delete source by ID."""
        model = await self._session.get(SourceModel, source_id)
        if not model:
            return False
        await self._session.delete(model)
        return True

    @staticmethod
    def _to_domain(model: SourceModel) -> Source:
        return Source(
            id=model.id,
            project_id=model.project_id,
            source_type=SourceType(model.source_type),
            name=model.name,
            credentials=model.credentials,
            config=model.config,
            is_active=model.is_active,
            last_synced_at=model.last_synced_at,
            created_at=model.created_at,
        )


class ItemRepositoryImpl:
    """SQLAlchemy implementation of ItemRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self._session = session

    async def upsert(self, item: DigestItem) -> UUID:
        """Insert or update an item using PostgreSQL upsert."""
        insert_stmt = insert(ItemModel).values(
            id=uuid4(),
            source_id=item.source_id,
            external_id=item.external_id,
            item_type=item.item_type.value,
            title=item.title,
            content=item.content,
            content_hash=item.content_hash,
            metadata_=item.metadata,
            external_url=item.external_url,
            external_created_at=item.external_created_at,
            external_updated_at=item.external_updated_at,
            fetched_at=datetime.now(UTC),
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_items_source_external",
            set_={
                "title": insert_stmt.excluded.title,
                "content": insert_stmt.excluded.content,
                "content_hash": insert_stmt.excluded.content_hash,
                "metadata_": insert_stmt.excluded.metadata_,
                "external_url": insert_stmt.excluded.external_url,
                "external_updated_at": insert_stmt.excluded.external_updated_at,
                "fetched_at": insert_stmt.excluded.fetched_at,
            },
        ).returning(ItemModel.id)

        result = await self._session.execute(upsert_stmt)
        row = result.scalar_one()
        return UUID(str(row)) if not isinstance(row, UUID) else row

    async def upsert_many(self, items: list[DigestItem]) -> list[UUID]:
        """Insert or update multiple items."""
        ids = []
        for item in items:
            item_id = await self.upsert(item)
            ids.append(item_id)
        return ids

    async def get_by_id(self, item_id: UUID) -> DigestItem | None:
        """Get item by ID."""
        model = await self._session.get(ItemModel, item_id)
        return self._to_domain(model) if model else None

    async def get_by_external_id(
        self,
        source_id: UUID,
        external_id: str,
    ) -> DigestItem | None:
        """Get item by source ID and external ID."""
        stmt = select(ItemModel).where(
            and_(
                ItemModel.source_id == source_id,
                ItemModel.external_id == external_id,
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_changed_since_last_digest(
        self,
        source_id: UUID,
    ) -> list[tuple[DigestItem, UUID]]:
        """Get items that have changed since they were last shown in a digest."""
        # Get the latest digest item record for each item
        # Compare current content_hash with content_hash_at_send
        subquery = (
            select(
                DigestItemModel.item_id,
                DigestItemModel.content_hash_at_send,
            )
            .join(DigestModel)
            .where(DigestModel.status == "sent")
            .distinct(DigestItemModel.item_id)
            .order_by(DigestItemModel.item_id, desc(DigestModel.sent_at))
            .subquery()
        )

        stmt = (
            select(ItemModel)
            .outerjoin(subquery, ItemModel.id == subquery.c.item_id)
            .where(
                and_(
                    ItemModel.source_id == source_id,
                    # Either never shown, or hash changed
                    (subquery.c.content_hash_at_send.is_(None))
                    | (ItemModel.content_hash != subquery.c.content_hash_at_send),
                )
            )
        )

        result = await self._session.execute(stmt)
        return [(self._to_domain(m), m.id) for m in result.scalars()]

    async def get_new_items(
        self,
        source_id: UUID,
        since: datetime,
    ) -> list[tuple[DigestItem, UUID]]:
        """Get items fetched since a given timestamp."""
        stmt = (
            select(ItemModel)
            .where(
                and_(
                    ItemModel.source_id == source_id,
                    ItemModel.fetched_at >= since,
                )
            )
            .order_by(desc(ItemModel.external_updated_at))
        )
        result = await self._session.execute(stmt)
        return [(self._to_domain(m), m.id) for m in result.scalars()]

    @staticmethod
    def _to_domain(model: ItemModel) -> DigestItem:
        return DigestItem(
            source_id=model.source_id,
            external_id=model.external_id,
            item_type=ItemType(model.item_type),
            title=model.title,
            content=model.content,
            content_hash=model.content_hash,
            metadata=model.metadata_,
            external_url=model.external_url,
            external_created_at=model.external_created_at,
            external_updated_at=model.external_updated_at,
        )


class DigestRepositoryImpl:
    """SQLAlchemy implementation of DigestRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self._session = session

    async def create(
        self,
        digest_type: str,
        scheduled_at: datetime | None = None,
    ) -> Digest:
        """Create a new digest."""
        model = DigestModel(
            digest_type=digest_type,
            scheduled_at=scheduled_at,
            status="pending",
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_id(self, digest_id: UUID) -> Digest | None:
        """Get digest by ID."""
        model = await self._session.get(DigestModel, digest_id)
        return self._to_domain(model) if model else None

    async def get_latest(self, digest_type: str | None = None) -> Digest | None:
        """Get the most recent digest."""
        stmt = select(DigestModel).order_by(desc(DigestModel.created_at)).limit(1)
        if digest_type:
            stmt = stmt.where(DigestModel.digest_type == digest_type)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_history(
        self,
        limit: int = 10,
        offset: int = 0,
        digest_type: str | None = None,
    ) -> list[Digest]:
        """Get digest history with pagination."""
        stmt = select(DigestModel).order_by(desc(DigestModel.created_at)).limit(limit).offset(offset)
        if digest_type:
            stmt = stmt.where(DigestModel.digest_type == digest_type)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def update_status(
        self,
        digest_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Update digest status."""
        stmt = update(DigestModel).where(DigestModel.id == digest_id).values(status=status, error_message=error_message)
        await self._session.execute(stmt)

    async def mark_sent(
        self,
        digest_id: UUID,
        telegram_message_id: int,
        content: str,
        item_count: int,
    ) -> None:
        """Mark digest as sent with delivery details."""
        stmt = (
            update(DigestModel)
            .where(DigestModel.id == digest_id)
            .values(
                status="sent",
                sent_at=datetime.now(UTC),
                telegram_message_id=telegram_message_id,
                content=content,
                item_count=item_count,
            )
        )
        await self._session.execute(stmt)

    async def add_items(
        self,
        digest_id: UUID,
        items: list[tuple[UUID, str]],  # (item_id, content_hash)
    ) -> None:
        """Add items to a digest."""
        for item_id, content_hash in items:
            model = DigestItemModel(
                digest_id=digest_id,
                item_id=item_id,
                content_hash_at_send=content_hash,
            )
            self._session.add(model)
        await self._session.flush()

    @staticmethod
    def _to_domain(model: DigestModel) -> Digest:
        return Digest(
            id=model.id,
            digest_type=DigestType(model.digest_type),
            status=DigestStatus(model.status),
            scheduled_at=model.scheduled_at,
            sent_at=model.sent_at,
            telegram_message_id=model.telegram_message_id,
            content=model.content,
            item_count=model.item_count,
            error_message=model.error_message,
            created_at=model.created_at,
        )


class ScheduleRepositoryImpl:
    """SQLAlchemy implementation of ScheduleRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self._session = session

    async def create(
        self,
        name: str,
        digest_type: str,
        cron_expression: str,
        timezone: str = "Europe/Lisbon",
        project_ids: list[UUID] | None = None,
    ) -> Schedule:
        """Create a new schedule."""
        model = ScheduleModel(
            name=name,
            digest_type=digest_type,
            cron_expression=cron_expression,
            timezone=timezone,
            project_ids=project_ids or [],
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_id(self, schedule_id: UUID) -> Schedule | None:
        """Get schedule by ID."""
        model = await self._session.get(ScheduleModel, schedule_id)
        return self._to_domain(model) if model else None

    async def get_active(self) -> list[Schedule]:
        """Get all active schedules."""
        stmt = select(ScheduleModel).where(ScheduleModel.is_active == True)  # noqa: E712
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def update(
        self,
        schedule_id: UUID,
        name: str | None = None,
        cron_expression: str | None = None,
        timezone: str | None = None,
        is_active: bool | None = None,
        project_ids: list[UUID] | None = None,
    ) -> Schedule | None:
        """Update schedule fields."""
        model = await self._session.get(ScheduleModel, schedule_id)
        if not model:
            return None
        if name is not None:
            model.name = name
        if cron_expression is not None:
            model.cron_expression = cron_expression
        if timezone is not None:
            model.timezone = timezone
        if is_active is not None:
            model.is_active = is_active
        if project_ids is not None:
            model.project_ids = project_ids
        await self._session.flush()
        return self._to_domain(model)

    async def delete(self, schedule_id: UUID) -> bool:
        """Delete schedule by ID."""
        model = await self._session.get(ScheduleModel, schedule_id)
        if not model:
            return False
        await self._session.delete(model)
        return True

    @staticmethod
    def _to_domain(model: ScheduleModel) -> Schedule:
        return Schedule(
            id=model.id,
            name=model.name,
            digest_type=DigestType(model.digest_type),
            cron_expression=model.cron_expression,
            timezone=model.timezone,
            is_active=model.is_active,
            project_ids=list(model.project_ids),
            created_at=model.created_at,
        )


class CollectorErrorRepositoryImpl:
    """SQLAlchemy implementation of CollectorErrorRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self._session = session

    async def create(
        self,
        source_id: UUID,
        error_type: str,
        error_message: str,
    ) -> CollectorError:
        """Record a new collector error."""
        model = CollectorErrorModel(
            source_id=source_id,
            error_type=error_type,
            error_message=error_message,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get_unresolved(
        self,
        source_id: UUID | None = None,
    ) -> list[CollectorError]:
        """Get unresolved errors, optionally filtered by source."""
        stmt = select(CollectorErrorModel).where(
            CollectorErrorModel.resolved == False  # noqa: E712
        )
        if source_id:
            stmt = stmt.where(CollectorErrorModel.source_id == source_id)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def mark_resolved(self, error_id: UUID) -> None:
        """Mark an error as resolved."""
        stmt = update(CollectorErrorModel).where(CollectorErrorModel.id == error_id).values(resolved=True)
        await self._session.execute(stmt)

    async def mark_all_resolved(self, source_id: UUID) -> None:
        """Mark all errors for a source as resolved."""
        stmt = (
            update(CollectorErrorModel)
            .where(
                and_(
                    CollectorErrorModel.source_id == source_id,
                    CollectorErrorModel.resolved == False,  # noqa: E712
                )
            )
            .values(resolved=True)
        )
        await self._session.execute(stmt)

    @staticmethod
    def _to_domain(model: CollectorErrorModel) -> CollectorError:
        return CollectorError(
            id=model.id,
            source_id=model.source_id,
            error_type=model.error_type or "unknown",
            error_message=model.error_message or "",
            resolved=model.resolved,
            created_at=model.created_at,
        )


class SettingsRepositoryImpl:
    """SQLAlchemy implementation of SettingsRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self._session = session

    async def get(self, key: str) -> Setting | None:
        """Get setting by key."""
        model = await self._session.get(SettingModel, key)
        return self._to_domain(model) if model else None

    async def get_all(self) -> list[Setting]:
        """Get all settings."""
        stmt = select(SettingModel).order_by(SettingModel.key)
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars()]

    async def set(self, key: str, value: Any) -> Setting:
        """Set a setting value (upsert)."""
        model = await self._session.get(SettingModel, key)
        if model:
            model.value = value
            model.updated_at = datetime.now(UTC)
        else:
            model = SettingModel(key=key, value=value)
            self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def delete(self, key: str) -> bool:
        """Delete setting by key."""
        model = await self._session.get(SettingModel, key)
        if not model:
            return False
        await self._session.delete(model)
        return True

    @staticmethod
    def _to_domain(model: SettingModel) -> Setting:
        return Setting(
            key=model.key,
            value=model.value,
            updated_at=model.updated_at,
        )
