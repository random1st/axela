"""Tests for Slack collector."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from axela.domain.enums import ItemType, SourceType
from axela.infrastructure.collectors.slack import SlackCollector


class TestSlackCollector:
    """Tests for SlackCollector."""

    @pytest.fixture
    def collector(self) -> SlackCollector:
        """Create a SlackCollector instance."""
        return SlackCollector()

    @pytest.fixture
    def valid_credentials(self) -> dict[str, Any]:
        """Return valid Slack bot token credentials."""
        return {"bot_token": "xoxb-test-token-12345"}

    @pytest.fixture
    def sample_channel_info(self) -> dict[str, Any]:
        """Sample channel info response."""
        return {
            "ok": True,
            "channel": {
                "id": "C01234567",
                "name": "general",
                "is_channel": True,
            },
        }

    @pytest.fixture
    def sample_messages(self) -> dict[str, Any]:
        """Sample messages response."""
        return {
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "ts": "1705329600.123456",
                    "user": "U01234567",
                    "text": "Hello, this is a test message!",
                    "reply_count": 0,
                },
                {
                    "type": "message",
                    "ts": "1705330200.789012",
                    "user": "U07654321",
                    "text": "This message has replies",
                    "reply_count": 2,
                    "thread_ts": "1705330200.789012",
                },
            ],
        }

    @pytest.fixture
    def sample_message(self) -> dict[str, Any]:
        """Single sample message."""
        return {
            "type": "message",
            "ts": "1705329600.123456",
            "user": "U01234567",
            "text": "Hello, this is a test message!",
            "reply_count": 0,
        }

    def test_source_type(self, collector: SlackCollector) -> None:
        """Test source_type property."""
        assert collector.source_type == SourceType.SLACK

    def test_parse_slack_ts(self, collector: SlackCollector) -> None:
        """Test Slack timestamp parsing."""
        result = collector._parse_slack_ts("1705329600.123456")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_slack_ts_empty(self, collector: SlackCollector) -> None:
        """Test parsing empty timestamp."""
        assert collector._parse_slack_ts("") is None
        assert collector._parse_slack_ts(None) is None

    def test_parse_slack_ts_invalid(self, collector: SlackCollector) -> None:
        """Test parsing invalid timestamp."""
        assert collector._parse_slack_ts("invalid") is None

    @pytest.mark.asyncio
    async def test_collect_success(
        self,
        collector: SlackCollector,
        valid_credentials: dict[str, Any],
        sample_channel_info: dict[str, Any],
        sample_messages: dict[str, Any],
    ) -> None:
        """Test successful collection."""
        mock_client = AsyncMock()

        # Mock responses
        mock_client.get.side_effect = [
            # Channel info
            MagicMock(json=lambda: sample_channel_info),
            # Messages
            MagicMock(json=lambda: sample_messages),
        ]

        with patch.object(collector, "get_client", return_value=mock_client):
            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={
                    "channel_ids": ["C01234567"],
                    "include_threads": False,
                },
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        assert len(items) == 2
        item = items[0]
        assert item.item_type == ItemType.MESSAGE
        assert item.title is not None
        assert "Hello, this is a test message!" in item.title

    @pytest.mark.asyncio
    async def test_collect_skips_bot_messages(
        self,
        collector: SlackCollector,
        valid_credentials: dict[str, Any],
        sample_channel_info: dict[str, Any],
    ) -> None:
        """Test that bot messages are skipped."""
        messages_with_bot = {
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "subtype": "bot_message",
                    "ts": "1705329600.123456",
                    "text": "Bot message",
                },
                {
                    "type": "message",
                    "ts": "1705330200.789012",
                    "user": "U01234567",
                    "text": "User message",
                },
            ],
        }

        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            MagicMock(json=lambda: sample_channel_info),
            MagicMock(json=lambda: messages_with_bot),
        ]

        with patch.object(collector, "get_client", return_value=mock_client):
            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={
                    "channel_ids": ["C01234567"],
                    "include_threads": False,
                },
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        # Only the user message should be collected
        assert len(items) == 1
        assert items[0].title is not None
        assert "User message" in items[0].title

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self,
        collector: SlackCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation success."""
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(json=lambda: {"ok": True, "user_id": "U01234567"})

        with patch.object(collector, "get_client", return_value=mock_client):
            result = await collector.validate_credentials(valid_credentials)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_credentials_failure(
        self,
        collector: SlackCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation failure."""
        mock_client = AsyncMock()
        mock_client.get.return_value = MagicMock(json=lambda: {"ok": False, "error": "invalid_auth"})

        with patch.object(collector, "get_client", return_value=mock_client):
            result = await collector.validate_credentials(valid_credentials)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_credentials_missing_token(
        self,
        collector: SlackCollector,
    ) -> None:
        """Test credential validation with missing token."""
        result = await collector.validate_credentials({})
        assert result is False

    def test_message_to_digest_item(
        self,
        collector: SlackCollector,
        sample_message: dict[str, Any],
    ) -> None:
        """Test message to DigestItem conversion."""
        source_id = str(uuid4())
        item = collector._message_to_digest_item(
            source_id,
            "C01234567",
            "general",
            sample_message,
        )

        assert item.source_id == UUID(source_id)
        assert item.external_id == "C01234567:1705329600.123456"
        assert item.item_type == ItemType.MESSAGE
        assert item.title is not None
        assert "#general" in item.title
        assert "Hello, this is a test message!" in item.title
        assert item.content["channel_name"] == "general"
        assert item.content["user"] == "U01234567"
        assert item.content["is_thread_reply"] is False
        assert item.metadata["channel"] == "general"

    def test_message_to_digest_item_thread_reply(
        self,
        collector: SlackCollector,
        sample_message: dict[str, Any],
    ) -> None:
        """Test thread reply conversion."""
        source_id = str(uuid4())
        sample_message["thread_ts"] = "1705329500.000000"

        item = collector._message_to_digest_item(
            source_id,
            "C01234567",
            "general",
            sample_message,
            is_thread_reply=True,
        )

        assert item.content["is_thread_reply"] is True
        assert item.metadata["is_thread_reply"] is True

    def test_message_to_digest_item_long_text(
        self,
        collector: SlackCollector,
    ) -> None:
        """Test long message text is truncated in title."""
        source_id = str(uuid4())
        long_text = "A" * 200  # Very long message

        message = {
            "ts": "1705329600.123456",
            "user": "U01234567",
            "text": long_text,
        }

        item = collector._message_to_digest_item(
            source_id,
            "C01234567",
            "general",
            message,
        )

        # Title should be truncated
        assert item.title is not None
        assert len(item.title) <= 120  # channel prefix + truncated text + ellipsis
        assert "..." in item.title

    def test_message_to_digest_item_empty_text(
        self,
        collector: SlackCollector,
    ) -> None:
        """Test message with empty text."""
        source_id = str(uuid4())

        message = {
            "ts": "1705329600.123456",
            "user": "U01234567",
            "text": "",
        }

        item = collector._message_to_digest_item(
            source_id,
            "C01234567",
            "general",
            message,
        )

        assert item.title is not None
        assert "(no message)" in item.title

    def test_message_to_digest_item_with_attachments(
        self,
        collector: SlackCollector,
    ) -> None:
        """Test message with attachments."""
        source_id = str(uuid4())

        message = {
            "ts": "1705329600.123456",
            "user": "U01234567",
            "text": "Check this out",
            "attachments": [{"title": "Link"}],
            "files": [{"id": "F01234567"}],
        }

        item = collector._message_to_digest_item(
            source_id,
            "C01234567",
            "general",
            message,
        )

        assert item.content["has_attachments"] is True
        assert item.content["has_files"] is True
