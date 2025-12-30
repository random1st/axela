"""Tests for Gmail collector."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from axela.domain.enums import ItemType, SourceType
from axela.infrastructure.collectors.gmail import GmailCollector


class TestGmailCollector:
    """Tests for GmailCollector."""

    @pytest.fixture
    def collector(self) -> GmailCollector:
        """Create a GmailCollector instance."""
        return GmailCollector()

    @pytest.fixture
    def valid_credentials(self) -> dict[str, Any]:
        """Return valid Gmail OAuth2 credentials."""
        return {
            "access_token": "ya29.test-access-token",
            "refresh_token": "1//test-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-client-secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }

    @pytest.fixture
    def sample_message_list(self) -> dict[str, Any]:
        """Sample Gmail message list response."""
        return {
            "messages": [
                {"id": "msg123", "threadId": "thread123"},
                {"id": "msg456", "threadId": "thread456"},
            ]
        }

    @pytest.fixture
    def sample_message(self) -> dict[str, Any]:
        """Sample Gmail message response."""
        return {
            "id": "msg123",
            "threadId": "thread123",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "This is a test email preview...",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "John Doe <john@example.com>"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": "Mon, 15 Jan 2024 10:30:00 +0000"},
                ],
                "body": {
                    "data": "VGhpcyBpcyB0aGUgZW1haWwgYm9keQ==",  # "This is the email body"
                },
            },
        }

    def test_source_type(self, collector: GmailCollector) -> None:
        """Test source_type property."""
        assert collector.source_type == SourceType.GMAIL

    def test_build_query_default(self, collector: GmailCollector) -> None:
        """Test default query generation."""
        since = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        query = collector._build_query({}, since)

        assert "after:2024/01/15" in query

    def test_build_query_custom(self, collector: GmailCollector) -> None:
        """Test custom query with date filter appended."""
        since = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        config = {"query": "is:unread"}
        query = collector._build_query(config, since)

        assert "is:unread" in query
        assert "after:2024/01/15" in query

    def test_build_query_custom_with_after(self, collector: GmailCollector) -> None:
        """Test custom query that already has after filter."""
        since = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        config = {"query": "is:unread after:2024/01/01"}
        query = collector._build_query(config, since)

        # Should not add another after filter
        assert query == "is:unread after:2024/01/01"

    def test_get_header(self, collector: GmailCollector) -> None:
        """Test header extraction."""
        headers = [
            {"name": "Subject", "value": "Test Subject"},
            {"name": "From", "value": "john@example.com"},
        ]

        assert collector._get_header(headers, "Subject") == "Test Subject"
        assert collector._get_header(headers, "From") == "john@example.com"
        assert collector._get_header(headers, "Missing") is None

    def test_get_header_case_insensitive(self, collector: GmailCollector) -> None:
        """Test header extraction is case insensitive."""
        headers = [{"name": "SUBJECT", "value": "Test"}]

        assert collector._get_header(headers, "subject") == "Test"
        assert collector._get_header(headers, "Subject") == "Test"

    def test_parse_email_date(self, collector: GmailCollector) -> None:
        """Test email date parsing."""
        date_str = "Mon, 15 Jan 2024 10:30:00 +0000"
        result = collector._parse_email_date(date_str)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_email_date_none(self, collector: GmailCollector) -> None:
        """Test email date parsing with None."""
        assert collector._parse_email_date(None) is None

    def test_parse_email_date_invalid(self, collector: GmailCollector) -> None:
        """Test email date parsing with invalid string."""
        assert collector._parse_email_date("invalid") is None

    def test_extract_sender_name(self, collector: GmailCollector) -> None:
        """Test sender name extraction."""
        assert collector._extract_sender_name("John Doe <john@example.com>") == "John Doe"
        assert collector._extract_sender_name('"Jane Doe" <jane@example.com>') == "Jane Doe"
        assert collector._extract_sender_name("plain@example.com") == "plain@example.com"

    def test_extract_body_preview_plain_text(self, collector: GmailCollector) -> None:
        """Test body preview extraction from plain text."""
        payload = {
            "mimeType": "text/plain",
            "body": {"data": "SGVsbG8gV29ybGQh"},  # "Hello World!"
        }

        preview = collector._extract_body_preview(payload)
        assert preview == "Hello World!"

    def test_extract_body_preview_html(self, collector: GmailCollector) -> None:
        """Test body preview extraction from HTML (strips tags)."""
        # Base64 of "<html><body><p>Hello World!</p></body></html>"
        payload = {
            "mimeType": "text/html",
            "body": {"data": "PGh0bWw+PGJvZHk+PHA+SGVsbG8gV29ybGQhPC9wPjwvYm9keT48L2h0bWw+"},
        }

        preview = collector._extract_body_preview(payload)
        assert "Hello World!" in preview
        assert "<" not in preview  # HTML tags stripped

    def test_extract_body_preview_multipart(self, collector: GmailCollector) -> None:
        """Test body preview extraction from multipart message."""
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": "UGxhaW4gdGV4dA=="},  # "Plain text"
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": "PHA+SFRNTDwvcD4="},  # "<p>HTML</p>"
                },
            ],
        }

        preview = collector._extract_body_preview(payload)
        assert preview == "Plain text"  # Prefers plain text

    def test_extract_body_preview_empty(self, collector: GmailCollector) -> None:
        """Test body preview extraction with no body."""
        payload = {"mimeType": "text/plain", "body": {}}
        assert collector._extract_body_preview(payload) == ""

    @pytest.mark.asyncio
    async def test_collect_success(
        self,
        collector: GmailCollector,
        valid_credentials: dict[str, Any],
        sample_message_list: dict[str, Any],
        sample_message: dict[str, Any],
    ) -> None:
        """Test successful collection."""
        mock_service = MagicMock()
        mock_users = MagicMock()
        mock_messages = MagicMock()

        # Setup chain: service.users().messages()
        mock_service.users.return_value = mock_users
        mock_users.messages.return_value = mock_messages

        # Mock list response
        mock_list = MagicMock()
        mock_list.execute.return_value = sample_message_list
        mock_messages.list.return_value = mock_list

        # Mock get response
        mock_get = MagicMock()
        mock_get.execute.return_value = sample_message
        mock_messages.get.return_value = mock_get

        with patch.object(collector, "_get_gmail_service", return_value=mock_service):
            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={},
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        assert len(items) == 2
        item = items[0]
        assert item.external_id == "msg123"
        assert item.item_type == ItemType.EMAIL
        assert item.title == "Test Subject"
        assert item.content["sender"] == "John Doe <john@example.com>"
        assert item.content["is_unread"] is True

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self,
        collector: GmailCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation success."""
        mock_service = MagicMock()
        mock_users = MagicMock()
        mock_get_profile = MagicMock()
        mock_get_profile.execute.return_value = {"emailAddress": "test@gmail.com"}

        mock_service.users.return_value = mock_users
        mock_users.getProfile.return_value = mock_get_profile

        with patch.object(collector, "_get_gmail_service", return_value=mock_service):
            result = await collector.validate_credentials(valid_credentials)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_credentials_failure(
        self,
        collector: GmailCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation failure."""
        with patch.object(collector, "_get_gmail_service", return_value=None):
            result = await collector.validate_credentials(valid_credentials)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_credentials_missing(
        self,
        collector: GmailCollector,
    ) -> None:
        """Test credential validation with missing credentials."""
        with patch.object(collector, "_get_gmail_service", return_value=None):
            result = await collector.validate_credentials({})

        assert result is False

    def test_message_to_digest_item(
        self,
        collector: GmailCollector,
        sample_message: dict[str, Any],
    ) -> None:
        """Test message to DigestItem conversion."""
        source_id = str(uuid4())
        item = collector._message_to_digest_item(source_id, sample_message)

        assert item.source_id == UUID(source_id)
        assert item.external_id == "msg123"
        assert item.item_type == ItemType.EMAIL
        assert item.title == "Test Subject"
        assert item.content["sender"] == "John Doe <john@example.com>"
        assert item.content["thread_id"] == "thread123"
        assert item.content["is_unread"] is True
        assert "INBOX" in item.content["labels"]
        assert item.external_url == "https://mail.google.com/mail/u/0/#inbox/msg123"
        assert item.metadata["sender"] == "John Doe"
