"""Base collector implementation."""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID

import httpx
import structlog

from axela.application.ports.collector import (
    AuthenticationError,
    CollectorError,
    NetworkError,
    RateLimitError,
)
from axela.config import get_settings
from axela.domain.enums import ItemType, SourceType
from axela.domain.models import DigestItem

logger = structlog.get_logger()


class BaseCollector(ABC):
    """Base class for all collectors.

    Provides common functionality like HTTP client management,
    content hashing, and error handling.
    """

    def __init__(self) -> None:
        """Initialize the collector."""
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """The type of source this collector handles."""
        ...

    @abstractmethod
    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect items from the source."""
        ...

    @abstractmethod
    async def validate_credentials(
        self,
        credentials: dict[str, Any],
    ) -> bool:
        """Validate credentials."""
        ...

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client.

        Returns:
            Configured httpx AsyncClient.

        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def get_since_datetime(self, since: datetime | None) -> datetime:
        """Get the datetime to fetch items since.

        Args:
            since: Provided since datetime, or None for default.

        Returns:
            Datetime to fetch items since.

        """
        if since is not None:
            return since

        # Default to initial_fetch_days ago
        return datetime.now(UTC) - timedelta(days=self._settings.initial_fetch_days)

    @staticmethod
    def compute_content_hash(content: dict[str, Any]) -> str:
        """Compute SHA-256 hash of content for deduplication.

        The hash is computed from a normalized JSON representation
        of the content, ensuring consistent hashing regardless of
        key ordering.

        Args:
            content: Content dictionary to hash.

        Returns:
            Hex-encoded SHA-256 hash.

        """
        # Sort keys and use separators without spaces for consistent hashing
        normalized = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode()).hexdigest()

    def create_digest_item(
        self,
        source_id: str | UUID,
        external_id: str,
        item_type: ItemType,
        title: str | None,
        content: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        external_url: str | None = None,
        external_created_at: datetime | None = None,
        external_updated_at: datetime | None = None,
    ) -> DigestItem:
        """Create a DigestItem with computed content hash.

        Args:
            source_id: ID of the source.
            external_id: External identifier from the source.
            item_type: Type of the item.
            title: Human-readable title.
            content: Full content dictionary.
            metadata: Additional metadata.
            external_url: Link to the item in the source.
            external_created_at: When the item was created.
            external_updated_at: When the item was last updated.

        Returns:
            DigestItem with computed content hash.

        """
        # Compute hash from key fields that indicate changes
        hash_content = {
            "title": title,
            "status": content.get("status"),
            "priority": content.get("priority"),
            "assignee": content.get("assignee"),
            "updated_at": (external_updated_at.isoformat() if external_updated_at else None),
        }
        content_hash = self.compute_content_hash(hash_content)

        return DigestItem(
            source_id=UUID(source_id) if isinstance(source_id, str) else source_id,
            external_id=external_id,
            item_type=item_type,
            title=title,
            content=content,
            content_hash=content_hash,
            metadata=metadata or {},
            external_url=external_url,
            external_created_at=external_created_at,
            external_updated_at=external_updated_at,
        )

    async def handle_response_error(
        self,
        response: httpx.Response,
        context: str = "",
    ) -> None:
        """Handle HTTP response errors.

        Args:
            response: HTTP response to check.
            context: Additional context for error messages.

        Raises:
            RateLimitError: If rate limited.
            NetworkError: For server errors.
            CollectorError: For other errors.

        """
        if response.is_success:
            return

        status = response.status_code
        prefix = f"{context}: " if context else ""

        if status == 429:
            retry_after = response.headers.get("Retry-After")
            msg = f"{prefix}Rate limit exceeded"
            raise RateLimitError(
                msg,
                retry_after=int(retry_after) if retry_after else None,
            )

        if status >= 500:
            msg = f"{prefix}Server error: {status}"
            raise NetworkError(msg)

        if status in {401, 403}:
            msg = f"{prefix}Authentication failed: {status}"
            raise AuthenticationError(msg)

        msg = f"{prefix}Request failed: {status}"
        raise CollectorError(
            msg,
            error_type="http",
            recoverable=status >= 500,
        )


class CollectorRegistry:
    """Registry for collector implementations."""

    _collectors: ClassVar[dict[SourceType, type[BaseCollector]]] = {}

    @classmethod
    def register(cls, source_type: SourceType) -> Any:
        """Register a collector class via decorator.

        Args:
            source_type: The source type this collector handles.

        Returns:
            Decorator function.

        """

        def decorator(collector_class: type[BaseCollector]) -> type[BaseCollector]:
            cls._collectors[source_type] = collector_class
            logger.info(
                "Collector registered",
                source_type=source_type,
                collector=collector_class.__name__,
            )
            return collector_class

        return decorator

    @classmethod
    def get(cls, source_type: SourceType) -> type[BaseCollector] | None:
        """Get a collector class by source type.

        Args:
            source_type: The source type to get collector for.

        Returns:
            Collector class or None if not registered.

        """
        return cls._collectors.get(source_type)

    @classmethod
    def get_all(cls) -> dict[SourceType, type[BaseCollector]]:
        """Get all registered collectors.

        Returns:
            Dictionary mapping source types to collector classes.

        """
        return cls._collectors.copy()

    @classmethod
    def create(cls, source_type: SourceType) -> BaseCollector | None:
        """Create a collector instance by source type.

        Args:
            source_type: The source type to create collector for.

        Returns:
            Collector instance or None if not registered.

        """
        collector_class = cls.get(source_type)
        if collector_class:
            return collector_class()
        return None
