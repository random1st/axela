"""Tests for Outlook Mail collector."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from axela.domain.enums import ItemType, SourceType
from axela.infrastructure.collectors.outlook_mail import OutlookMailCollector


class TestOutlookMailCollector:
    """Tests for OutlookMailCollector."""

    @pytest.fixture
    def collector(self) -> OutlookMailCollector:
        """Create an OutlookMailCollector instance."""
        return OutlookMailCollector()

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
    def sample_messages_response(self) -> dict[str, Any]:
        """Sample Microsoft Graph messages response."""
        return {
            "value": [
                {
                    "id": "AAMkAGI2TG93AAA=",
                    "subject": "Important Meeting Tomorrow",
                    "bodyPreview": "Please join us for the quarterly review...",
                    "receivedDateTime": "2024-01-15T10:30:00Z",
                    "isRead": False,
                    "hasAttachments": True,
                    "importance": "high",
                    "webLink": "https://outlook.office365.com/owa/?ItemID=...",
                    "from": {
                        "emailAddress": {
                            "name": "John Doe",
                            "address": "john@example.com",
                        }
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "name": "Me",
                                "address": "me@example.com",
                            }
                        }
                    ],
                    "flag": {"flagStatus": "notFlagged"},
                    "categories": ["Work"],
                },
                {
                    "id": "AAMkAGI2TG94AAA=",
                    "subject": "Weekly Update",
                    "bodyPreview": "Here's the weekly summary...",
                    "receivedDateTime": "2024-01-15T09:00:00Z",
                    "isRead": True,
                    "hasAttachments": False,
                    "importance": "normal",
                    "webLink": "https://outlook.office365.com/owa/?ItemID=...",
                    "from": {
                        "emailAddress": {
                            "name": "Jane Smith",
                            "address": "jane@example.com",
                        }
                    },
                    "toRecipients": [],
                    "flag": {"flagStatus": "flagged"},
                    "categories": [],
                },
            ]
        }

    @pytest.fixture
    def sample_message(self) -> dict[str, Any]:
        """Single sample message."""
        return {
            "id": "AAMkAGI2TG93AAA=",
            "subject": "Test Subject",
            "bodyPreview": "This is a preview...",
            "receivedDateTime": "2024-01-15T10:30:00Z",
            "isRead": False,
            "hasAttachments": True,
            "importance": "high",
            "webLink": "https://outlook.office365.com/owa/?ItemID=test",
            "from": {
                "emailAddress": {
                    "name": "John Doe",
                    "address": "john@example.com",
                }
            },
            "toRecipients": [{"emailAddress": {"name": "Me", "address": "me@example.com"}}],
            "flag": {"flagStatus": "flagged"},
            "categories": ["Important", "Work"],
        }

    def test_source_type(self, collector: OutlookMailCollector) -> None:
        """Test source_type property."""
        assert collector.source_type == SourceType.OUTLOOK_MAIL

    def test_parse_graph_datetime(self, collector: OutlookMailCollector) -> None:
        """Test Microsoft Graph datetime parsing."""
        result = collector._parse_graph_datetime("2024-01-15T10:30:00Z")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_graph_datetime_with_offset(self, collector: OutlookMailCollector) -> None:
        """Test parsing datetime with offset."""
        result = collector._parse_graph_datetime("2024-01-15T10:30:00+00:00")

        assert result is not None
        assert result.year == 2024

    def test_parse_graph_datetime_none(self, collector: OutlookMailCollector) -> None:
        """Test parsing None datetime."""
        assert collector._parse_graph_datetime(None) is None

    def test_parse_graph_datetime_invalid(self, collector: OutlookMailCollector) -> None:
        """Test parsing invalid datetime."""
        assert collector._parse_graph_datetime("invalid") is None

    @pytest.mark.asyncio
    async def test_collect_success(
        self,
        collector: OutlookMailCollector,
        valid_credentials: dict[str, Any],
        sample_messages_response: dict[str, Any],
    ) -> None:
        """Test successful collection."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = sample_messages_response
        mock_client.get.return_value = mock_response

        with pytest.MonkeyPatch.context() as m:
            m.setattr(collector, "get_client", AsyncMock(return_value=mock_client))

            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={"folders": ["inbox"]},
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        assert len(items) == 2
        item = items[0]
        assert item.external_id == "AAMkAGI2TG93AAA="
        assert item.item_type == ItemType.EMAIL
        assert item.title == "Important Meeting Tomorrow"
        assert item.content["is_read"] is False
        assert item.content["has_attachments"] is True
        assert item.content["importance"] == "high"

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self,
        collector: OutlookMailCollector,
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
        collector: OutlookMailCollector,
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
        collector: OutlookMailCollector,
    ) -> None:
        """Test credential validation with missing token."""
        result = await collector.validate_credentials({})
        assert result is False

    def test_message_to_digest_item(
        self,
        collector: OutlookMailCollector,
        sample_message: dict[str, Any],
    ) -> None:
        """Test message to DigestItem conversion."""
        source_id = str(uuid4())
        item = collector._message_to_digest_item(source_id, "inbox", sample_message)

        assert item.source_id == UUID(source_id)
        assert item.external_id == "AAMkAGI2TG93AAA="
        assert item.item_type == ItemType.EMAIL
        assert item.title == "Test Subject"
        assert item.content["folder"] == "inbox"
        assert item.content["sender"] == "John Doe <john@example.com>"
        assert item.content["sender_name"] == "John Doe"
        assert item.content["sender_email"] == "john@example.com"
        assert item.content["is_read"] is False
        assert item.content["has_attachments"] is True
        assert item.content["importance"] == "high"
        assert item.content["is_flagged"] is True
        assert "Important" in item.content["categories"]
        assert "me@example.com" in item.content["to"]
        assert item.external_url == "https://outlook.office365.com/owa/?ItemID=test"
        assert item.metadata["sender"] == "John Doe"
        assert item.metadata["is_flagged"] is True

    def test_message_to_digest_item_no_sender_name(
        self,
        collector: OutlookMailCollector,
    ) -> None:
        """Test message without sender name."""
        source_id = str(uuid4())
        message = {
            "id": "test123",
            "subject": "Test",
            "from": {
                "emailAddress": {
                    "name": "",
                    "address": "noreply@example.com",
                }
            },
            "toRecipients": [],
            "receivedDateTime": "2024-01-15T10:00:00Z",
            "isRead": True,
            "hasAttachments": False,
            "importance": "normal",
            "flag": {"flagStatus": "notFlagged"},
            "categories": [],
        }

        item = collector._message_to_digest_item(source_id, "inbox", message)

        assert item.content["sender"] == "noreply@example.com"
        assert item.metadata["sender"] == "noreply@example.com"

    def test_message_to_digest_item_no_subject(
        self,
        collector: OutlookMailCollector,
    ) -> None:
        """Test message without subject."""
        source_id = str(uuid4())
        message = {
            "id": "test123",
            "from": {
                "emailAddress": {
                    "name": "Sender",
                    "address": "sender@example.com",
                }
            },
            "toRecipients": [],
            "receivedDateTime": "2024-01-15T10:00:00Z",
            "isRead": True,
            "hasAttachments": False,
            "importance": "normal",
            "flag": {"flagStatus": "notFlagged"},
            "categories": [],
        }

        item = collector._message_to_digest_item(source_id, "inbox", message)

        assert item.title == "(No Subject)"
