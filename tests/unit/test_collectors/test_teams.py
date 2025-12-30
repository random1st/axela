"""Tests for Microsoft Teams collector."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from axela.domain.enums import ItemType, SourceType
from axela.infrastructure.collectors.teams import TeamsCollector


class TestTeamsCollector:
    """Tests for TeamsCollector."""

    @pytest.fixture
    def collector(self) -> TeamsCollector:
        """Create a TeamsCollector instance."""
        return TeamsCollector()

    @pytest.fixture
    def valid_credentials(self) -> dict[str, Any]:
        """Return valid Microsoft Graph OAuth2 credentials."""
        return {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.test",
            "refresh_token": "0.ATest-token",
            "client_id": "test-client-id",
            "client_secret": "test-secret",
            "tenant_id": "test-tenant",
        }

    @pytest.fixture
    def sample_channels_response(self) -> dict[str, Any]:
        """Sample channels response."""
        return {
            "value": [
                {
                    "id": "channel123",
                    "displayName": "General",
                },
                {
                    "id": "channel456",
                    "displayName": "Development",
                },
            ]
        }

    @pytest.fixture
    def sample_messages_response(self) -> dict[str, Any]:
        """Sample messages response."""
        return {
            "value": [
                {
                    "id": "msg123",
                    "body": {
                        "contentType": "text",
                        "content": "Hello team! This is a test message.",
                    },
                    "from": {
                        "user": {
                            "id": "user123",
                            "displayName": "John Developer",
                        }
                    },
                    "createdDateTime": "2024-01-15T10:00:00Z",
                    "lastModifiedDateTime": "2024-01-15T10:00:00Z",
                    "importance": "normal",
                    "attachments": [],
                    "mentions": [],
                },
                {
                    "id": "msg456",
                    "body": {
                        "contentType": "html",
                        "content": "<p>Important <b>update</b>!</p>",
                    },
                    "from": {
                        "user": {
                            "id": "user456",
                            "displayName": "Jane Manager",
                        }
                    },
                    "createdDateTime": "2024-01-15T11:00:00Z",
                    "lastModifiedDateTime": "2024-01-15T11:30:00Z",
                    "importance": "high",
                    "attachments": [{"id": "att1"}],
                    "mentions": [{"mentioned": {"user": {"displayName": "John Developer"}}}],
                },
            ]
        }

    @pytest.fixture
    def sample_message(self) -> dict[str, Any]:
        """Single sample message."""
        return {
            "id": "msg123",
            "body": {
                "contentType": "text",
                "content": "Hello team! This is a test message.",
            },
            "from": {
                "user": {
                    "id": "user123",
                    "displayName": "John Developer",
                }
            },
            "createdDateTime": "2024-01-15T10:00:00Z",
            "lastModifiedDateTime": "2024-01-15T10:00:00Z",
            "importance": "normal",
            "attachments": [],
            "mentions": [],
        }

    def test_source_type(self, collector: TeamsCollector) -> None:
        """Test source_type property."""
        assert collector.source_type == SourceType.TEAMS

    def test_parse_graph_datetime(self, collector: TeamsCollector) -> None:
        """Test Microsoft Graph datetime parsing."""
        result = collector._parse_graph_datetime("2024-01-15T10:30:00Z")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_graph_datetime_with_offset(self, collector: TeamsCollector) -> None:
        """Test parsing datetime with offset."""
        result = collector._parse_graph_datetime("2024-01-15T10:30:00+00:00")

        assert result is not None
        assert result.year == 2024

    def test_parse_graph_datetime_none(self, collector: TeamsCollector) -> None:
        """Test parsing None datetime."""
        assert collector._parse_graph_datetime(None) is None

    def test_parse_graph_datetime_invalid(self, collector: TeamsCollector) -> None:
        """Test parsing invalid datetime."""
        assert collector._parse_graph_datetime("invalid") is None

    @pytest.mark.asyncio
    async def test_collect_success(
        self,
        collector: TeamsCollector,
        valid_credentials: dict[str, Any],
        sample_channels_response: dict[str, Any],
        sample_messages_response: dict[str, Any],
    ) -> None:
        """Test successful collection."""
        mock_client = AsyncMock()

        # Mock responses for different endpoints
        team_response = MagicMock()
        team_response.is_success = True
        team_response.json.return_value = {"displayName": "Engineering Team"}

        channels_response = MagicMock()
        channels_response.is_success = True
        channels_response.json.return_value = sample_channels_response

        messages_response = MagicMock()
        messages_response.is_success = True
        messages_response.json.return_value = sample_messages_response

        mock_client.get.side_effect = [
            team_response,  # Team info
            channels_response,  # Channels list
            messages_response,  # Messages for channel 1
            messages_response,  # Messages for channel 2
        ]

        with pytest.MonkeyPatch.context() as m:
            m.setattr(collector, "get_client", AsyncMock(return_value=mock_client))

            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={
                    "team_ids": ["team123"],
                    "include_replies": False,
                },
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        # 2 channels × 2 messages each = 4 items
        assert len(items) == 4
        item = items[0]
        assert item.item_type == ItemType.MESSAGE
        assert item.title is not None
        assert "Hello team!" in item.title

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self,
        collector: TeamsCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation success."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_client.get.return_value = mock_response

        with pytest.MonkeyPatch.context() as m:
            m.setattr(collector, "get_client", AsyncMock(return_value=mock_client))
            result = await collector.validate_credentials(valid_credentials)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_credentials_failure(
        self,
        collector: TeamsCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation failure."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_client.get.return_value = mock_response

        with pytest.MonkeyPatch.context() as m:
            m.setattr(collector, "get_client", AsyncMock(return_value=mock_client))
            result = await collector.validate_credentials(valid_credentials)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_credentials_missing_token(
        self,
        collector: TeamsCollector,
    ) -> None:
        """Test credential validation with missing token."""
        result = await collector.validate_credentials({})
        assert result is False

    def test_message_to_digest_item(
        self,
        collector: TeamsCollector,
        sample_message: dict[str, Any],
    ) -> None:
        """Test message to DigestItem conversion."""
        source_id = str(uuid4())
        item = collector._message_to_digest_item(
            source_id,
            "team123",
            "Engineering Team",
            "channel123",
            "General",
            sample_message,
        )

        assert item.source_id == UUID(source_id)
        assert item.external_id == "msg123"
        assert item.item_type == ItemType.MESSAGE
        assert item.title is not None
        assert "[Engineering Team] #General" in item.title
        assert "Hello team!" in item.title
        assert item.content["team_name"] == "Engineering Team"
        assert item.content["channel_name"] == "General"
        assert item.content["sender_name"] == "John Developer"
        assert item.content["is_reply"] is False
        assert item.content["importance"] == "normal"
        assert item.metadata["team"] == "Engineering Team"
        assert item.metadata["channel"] == "General"

    def test_message_to_digest_item_html_content(
        self,
        collector: TeamsCollector,
    ) -> None:
        """Test message with HTML content (tags stripped)."""
        source_id = str(uuid4())
        message = {
            "id": "msg123",
            "body": {
                "contentType": "html",
                "content": "<p>Important <b>update</b>!</p>",
            },
            "from": {
                "user": {
                    "id": "user123",
                    "displayName": "John",
                }
            },
            "createdDateTime": "2024-01-15T10:00:00Z",
        }

        item = collector._message_to_digest_item(
            source_id,
            "team123",
            "Team",
            "channel123",
            "General",
            message,
        )

        # HTML tags should be stripped
        assert "<p>" not in item.content["body"]
        assert "<b>" not in item.content["body"]
        assert "Important update!" in item.content["body"]

    def test_message_to_digest_item_reply(
        self,
        collector: TeamsCollector,
        sample_message: dict[str, Any],
    ) -> None:
        """Test reply message conversion."""
        source_id = str(uuid4())
        item = collector._message_to_digest_item(
            source_id,
            "team123",
            "Team",
            "channel123",
            "General",
            sample_message,
            is_reply=True,
        )

        assert item.content["is_reply"] is True
        assert item.metadata["is_reply"] is True

    def test_message_to_digest_item_with_attachments(
        self,
        collector: TeamsCollector,
    ) -> None:
        """Test message with attachments."""
        source_id = str(uuid4())
        message = {
            "id": "msg123",
            "body": {"contentType": "text", "content": "Check attachment"},
            "from": {"user": {"id": "u1", "displayName": "User"}},
            "createdDateTime": "2024-01-15T10:00:00Z",
            "attachments": [{"id": "att1"}, {"id": "att2"}],
            "mentions": [],
        }

        item = collector._message_to_digest_item(
            source_id,
            "team123",
            "Team",
            "channel123",
            "General",
            message,
        )

        assert item.content["has_attachments"] is True

    def test_message_to_digest_item_with_mentions(
        self,
        collector: TeamsCollector,
    ) -> None:
        """Test message with mentions."""
        source_id = str(uuid4())
        message = {
            "id": "msg123",
            "body": {"contentType": "text", "content": "@John, please review"},
            "from": {"user": {"id": "u1", "displayName": "User"}},
            "createdDateTime": "2024-01-15T10:00:00Z",
            "attachments": [],
            "mentions": [
                {"mentioned": {"user": {"displayName": "John Developer"}}},
                {"mentioned": {"user": {"displayName": "Jane Manager"}}},
            ],
        }

        item = collector._message_to_digest_item(
            source_id,
            "team123",
            "Team",
            "channel123",
            "General",
            message,
        )

        assert "John Developer" in item.content["mentions"]
        assert "Jane Manager" in item.content["mentions"]

    def test_message_to_digest_item_long_content(
        self,
        collector: TeamsCollector,
    ) -> None:
        """Test long message content is truncated in title."""
        source_id = str(uuid4())
        long_content = "A" * 200

        message = {
            "id": "msg123",
            "body": {"contentType": "text", "content": long_content},
            "from": {"user": {"id": "u1", "displayName": "User"}},
            "createdDateTime": "2024-01-15T10:00:00Z",
        }

        item = collector._message_to_digest_item(
            source_id,
            "team123",
            "Team",
            "channel123",
            "General",
            message,
        )

        # Title should be truncated
        assert item.title is not None
        assert len(item.title) <= 150  # team + channel + truncated text + ellipsis
        assert "..." in item.title
