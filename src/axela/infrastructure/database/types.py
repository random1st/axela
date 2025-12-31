"""Cross-platform SQLAlchemy types for PostgreSQL and SQLite support."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Text
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Dialect
from sqlalchemy.types import CHAR, TypeDecorator, TypeEngine


class GUID(TypeDecorator[UUID]):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type when available, otherwise uses CHAR(36).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        """Return dialect-specific type implementation."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: UUID | str | None, dialect: Dialect) -> Any:
        """Convert Python UUID to database format."""
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, UUID) else UUID(value)
        return str(value) if isinstance(value, UUID) else value

    def process_result_value(self, value: str | UUID | None, dialect: Dialect) -> UUID | None:  # noqa: ARG002
        """Convert database value to Python UUID."""
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(value)


class JSONB(TypeDecorator[dict[str, Any]]):
    """Platform-independent JSON type.

    Uses PostgreSQL's JSONB when available, otherwise uses JSON.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        """Return dialect-specific type implementation."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())


class UUIDArray(TypeDecorator[list[UUID]]):
    """Platform-independent UUID array type.

    Uses PostgreSQL's ARRAY(UUID) when available, otherwise stores as JSON text.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        """Return dialect-specific type implementation."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_ARRAY(PG_UUID(as_uuid=True)))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: list[UUID] | None, dialect: Dialect) -> Any:
        """Convert Python list of UUIDs to database format."""
        if value is None:
            return [] if dialect.name == "postgresql" else "[]"
        if dialect.name == "postgresql":
            return value
        # For SQLite, serialize to JSON string
        return json.dumps([str(uid) for uid in value])

    def process_result_value(self, value: Any, dialect: Dialect) -> list[UUID]:  # noqa: ARG002
        """Convert database value to Python list of UUIDs."""
        if value is None:
            return []
        if isinstance(value, list):
            # PostgreSQL returns native list
            return value if value else []
        # For SQLite, deserialize from JSON string
        if isinstance(value, str):
            try:
                return [UUID(uid) for uid in json.loads(value)]
            except (json.JSONDecodeError, ValueError):
                return []
        return []
