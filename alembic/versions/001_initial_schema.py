"""Initial schema with all tables.

Revision ID: 001
Revises:
Create Date: 2024-12-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Projects table
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("color", sa.String(7)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Sources table
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("credentials", postgresql.JSONB, nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Items table
    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("item_type", sa.String(50), nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("external_url", sa.Text),
        sa.Column("external_created_at", sa.DateTime(timezone=True)),
        sa.Column("external_updated_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_items_source_external"),
    )
    op.create_index("idx_items_source_external", "items", ["source_id", "external_id"])
    op.create_index("idx_items_fetched_at", "items", ["fetched_at"])
    op.create_index("idx_items_content_hash", "items", ["content_hash"])

    # Digests table
    op.create_table(
        "digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("digest_type", sa.String(20), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("telegram_message_id", sa.Integer),
        sa.Column("content", sa.Text),
        sa.Column("item_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_digests_sent_at", "digests", ["sent_at"])

    # Digest items table
    op.create_table(
        "digest_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "digest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("digests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash_at_send", sa.String(64), nullable=False),
        sa.UniqueConstraint("digest_id", "item_id", name="uq_digest_items"),
    )

    # Schedules table
    op.create_table(
        "schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("digest_type", sa.String(20), nullable=False),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="'Europe/Lisbon'"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "project_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_schedules_active",
        "schedules",
        ["is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # Collector errors table
    op.create_table(
        "collector_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(100)),
        sa.Column("error_message", sa.Text),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Settings table (key-value store)
    op.create_table(
        "settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Insert default settings
    op.execute(
        """
        INSERT INTO settings (key, value, updated_at) VALUES
        ('telegram_chat_id', 'null', NOW()),
        ('digest_language', '"ru"', NOW())
        """
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("collector_errors")
    op.drop_index("idx_schedules_active", table_name="schedules")
    op.drop_table("schedules")
    op.drop_table("digest_items")
    op.drop_index("idx_digests_sent_at", table_name="digests")
    op.drop_table("digests")
    op.drop_index("idx_items_content_hash", table_name="items")
    op.drop_index("idx_items_fetched_at", table_name="items")
    op.drop_index("idx_items_source_external", table_name="items")
    op.drop_table("items")
    op.drop_table("sources")
    op.drop_table("projects")
