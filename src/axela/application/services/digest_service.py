"""Digest service - orchestrates collection, formatting, and delivery."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from axela.application.ports.collector import CollectorError
from axela.domain.enums import DigestStatus, DigestType
from axela.domain.events import (
    CollectionCompleted,
    CollectionStarted,
    CollectorFailed,
    DigestFailed,
    DigestReady,
    DigestSent,
)
from axela.domain.models import DigestItem, Project, Source
from axela.infrastructure.bus.memory import InMemoryMessageBus
from axela.infrastructure.collectors.base import CollectorRegistry
from axela.infrastructure.database.repository import (
    CollectorErrorRepositoryImpl,
    DigestRepositoryImpl,
    ItemRepositoryImpl,
    ProjectRepositoryImpl,
    SettingsRepositoryImpl,
    SourceRepositoryImpl,
)
from axela.infrastructure.telegram.formatter import format_digest

logger = structlog.get_logger()


class DigestService:
    """Service for generating and sending digests.

    Orchestrates the poll-before-digest pattern:
    1. When digest is scheduled, collect from all active sources
    2. Identify changed items (content_hash differs from last shown)
    3. Format digest message grouped by project
    4. Send via Telegram
    5. Record what was shown for deduplication
    """

    def __init__(
        self,
        session: AsyncSession,
        message_bus: InMemoryMessageBus,
    ) -> None:
        """Initialize the digest service.

        Args:
            session: Database session.
            message_bus: Event bus for publishing events.

        """
        self._session = session
        self._bus = message_bus

        # Initialize repositories
        self._projects = ProjectRepositoryImpl(session)
        self._sources = SourceRepositoryImpl(session)
        self._items = ItemRepositoryImpl(session)
        self._digests = DigestRepositoryImpl(session)
        self._errors = CollectorErrorRepositoryImpl(session)
        self._settings = SettingsRepositoryImpl(session)

    async def generate_digest(
        self,
        digest_type: DigestType,
        project_ids: list[UUID] | None = None,
    ) -> UUID:
        """Generate a digest by collecting from all sources and formatting.

        Args:
            digest_type: Type of digest to generate.
            project_ids: Optional list of project IDs to include.
                        If None, includes all projects.

        Returns:
            ID of the created digest.

        """
        log = logger.bind(digest_type=digest_type)
        log.info("Starting digest generation")

        # Create digest record
        digest = await self._digests.create(
            digest_type=digest_type.value,
            scheduled_at=datetime.now(UTC),
        )
        digest_id = digest.id

        try:
            # Update status to collecting
            await self._digests.update_status(digest_id, DigestStatus.COLLECTING.value)

            # Get sources to collect from
            sources = await self._get_sources_for_digest(project_ids)
            log.info("Collecting from sources", source_count=len(sources))

            # Collect from all sources
            all_items: list[tuple[DigestItem, UUID, Source]] = []
            for source in sources:
                items = await self._collect_from_source(source, digest_id)
                all_items.extend([(item, item_id, source) for item, item_id in items])

            if not all_items:
                log.info("No new items to include in digest")
                await self._digests.update_status(digest_id, DigestStatus.SENT.value)
                return digest_id

            # Update status to formatting
            await self._digests.update_status(digest_id, DigestStatus.FORMATTING.value)

            # Group items by project
            projects = await self._projects.get_all()
            project_map = {p.id: p for p in projects}

            # Format the digest
            content = await self._format_digest(
                digest_type=digest_type,
                items=all_items,
                project_map=project_map,
            )

            # Publish digest ready event
            await self._bus.publish(
                DigestReady(
                    digest_id=digest_id,
                    content=content,
                    item_count=len(all_items),
                )
            )

            # Record items shown in this digest
            await self._digests.add_items(
                digest_id,
                [(item_id, item.content_hash) for item, item_id, _ in all_items],
            )

            log.info(
                "Digest generated successfully",
                item_count=len(all_items),
                content_length=len(content),
            )

        except Exception as e:
            log.exception("Digest generation failed", error=str(e), exc_info=e)
            await self._digests.update_status(
                digest_id,
                DigestStatus.FAILED.value,
                error_message=str(e),
            )
            await self._bus.publish(DigestFailed(digest_id=digest_id, error_message=str(e)))
            raise

        return digest_id

    async def _get_sources_for_digest(
        self,
        project_ids: list[UUID] | None,
    ) -> list[Source]:
        """Get sources to collect from for a digest.

        Args:
            project_ids: Optional list of project IDs to filter by.

        Returns:
            List of active sources.

        """
        sources = await self._sources.get_active()

        if project_ids:
            sources = [s for s in sources if s.project_id in project_ids]

        return sources

    async def _collect_from_source(
        self,
        source: Source,
        digest_id: UUID,
    ) -> list[tuple[DigestItem, UUID]]:
        """Collect items from a single source.

        Args:
            source: Source to collect from.
            digest_id: ID of the current digest.

        Returns:
            List of (DigestItem, item_id) tuples.

        """
        log = logger.bind(
            source_id=str(source.id),
            source_type=source.source_type,
            source_name=source.name,
        )

        # Publish collection started event
        await self._bus.publish(CollectionStarted(source_id=source.id, digest_id=digest_id))

        collector = None
        result: list[tuple[DigestItem, UUID]] = []

        try:
            # Get collector for this source type
            collector = CollectorRegistry.create(source.source_type)
            if not collector:
                log.warning("No collector registered for source type")
                return result

            # Collect items
            items = await collector.collect(
                source_id=str(source.id),
                credentials=source.credentials,
                config=source.config,
                since=source.last_synced_at,
            )

            # Store items in database
            await self._items.upsert_many(items)

            # Update last synced timestamp
            await self._sources.update_last_synced(source.id, datetime.now(UTC))

            # Mark any previous errors as resolved
            await self._errors.mark_all_resolved(source.id)

            # Get changed items (deduplication)
            result = await self._items.get_changed_since_last_digest(source.id)

            # Publish collection completed event
            await self._bus.publish(
                CollectionCompleted(
                    source_id=source.id,
                    digest_id=digest_id,
                    items_count=len(items),
                    new_items_count=len(result),
                )
            )

            log.info(
                "Collection completed",
                total_items=len(items),
                changed_items=len(result),
            )

        except CollectorError as e:
            log.exception("Collector error", error_type=e.error_type, error=str(e))

            # Record error
            await self._errors.create(
                source_id=source.id,
                error_type=e.error_type,
                error_message=str(e),
            )

            # Publish collector failed event
            await self._bus.publish(
                CollectorFailed(
                    source_id=source.id,
                    error_type=e.error_type,
                    error_message=str(e),
                )
            )

        except Exception as e:
            log.exception("Unexpected error during collection", error=str(e), exc_info=e)

            # Record error
            await self._errors.create(
                source_id=source.id,
                error_type="unexpected",
                error_message=str(e),
            )

            # Publish collector failed event
            await self._bus.publish(
                CollectorFailed(
                    source_id=source.id,
                    error_type="unexpected",
                    error_message=str(e),
                )
            )

        finally:
            # Close collector resources
            if collector:
                await collector.close()

        return result

    async def _format_digest(
        self,
        digest_type: DigestType,
        items: list[tuple[DigestItem, UUID, Source]],
        project_map: dict[UUID, Project],
    ) -> str:
        """Format items into a digest message.

        Args:
            digest_type: Type of digest.
            items: List of (item, item_id, source) tuples.
            project_map: Mapping of project IDs to Project objects.

        Returns:
            Formatted digest message.

        """
        # Get language setting
        language = "ru"
        lang_setting = await self._settings.get("digest_language")
        if lang_setting and isinstance(lang_setting.value, str):
            language = lang_setting.value

        # Convert to format expected by formatter: (DigestItem, item_id, Project)
        formatter_items: list[tuple[DigestItem, UUID, Project]] = []
        for item, item_id, source in items:
            project = project_map.get(source.project_id)
            if project:
                formatter_items.append((item, item_id, project))

        return format_digest(formatter_items, digest_type, language)

    async def mark_digest_sent(
        self,
        digest_id: UUID,
        telegram_message_id: int,
        content: str,
        item_count: int,
    ) -> None:
        """Mark a digest as sent after Telegram delivery.

        Args:
            digest_id: ID of the digest.
            telegram_message_id: Telegram message ID.
            content: Rendered content.
            item_count: Number of items in digest.

        """
        await self._digests.mark_sent(
            digest_id,
            telegram_message_id,
            content,
            item_count,
        )

        await self._bus.publish(
            DigestSent(
                digest_id=digest_id,
                telegram_message_id=telegram_message_id,
            )
        )

        logger.info(
            "Digest marked as sent",
            digest_id=str(digest_id),
            telegram_message_id=telegram_message_id,
        )
