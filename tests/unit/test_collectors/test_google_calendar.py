"""Tests for Google Calendar collector."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from axela.domain.enums import ItemType, SourceType
from axela.infrastructure.collectors.google_calendar import GoogleCalendarCollector


class TestGoogleCalendarCollector:
    """Tests for GoogleCalendarCollector."""

    @pytest.fixture
    def collector(self) -> GoogleCalendarCollector:
        """Create a GoogleCalendarCollector instance."""
        return GoogleCalendarCollector()

    @pytest.fixture
    def valid_credentials(self) -> dict[str, Any]:
        """Return valid Google OAuth2 credentials."""
        return {
            "access_token": "ya29.test-access-token",
            "refresh_token": "1//test-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-client-secret",
            "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
        }

    @pytest.fixture
    def sample_events_response(self) -> dict[str, Any]:
        """Sample Calendar events list response."""
        return {
            "items": [
                {
                    "id": "event123",
                    "summary": "Team Meeting",
                    "description": "Weekly team sync",
                    "location": "Conference Room A",
                    "htmlLink": "https://calendar.google.com/event?eid=event123",
                    "start": {"dateTime": "2024-01-15T10:00:00+00:00"},
                    "end": {"dateTime": "2024-01-15T11:00:00+00:00"},
                    "status": "confirmed",
                    "organizer": {
                        "email": "organizer@example.com",
                        "displayName": "Jane Doe",
                    },
                    "attendees": [
                        {"email": "attendee1@example.com"},
                        {"email": "attendee2@example.com"},
                    ],
                    "created": "2024-01-10T08:00:00.000Z",
                    "updated": "2024-01-14T09:00:00.000Z",
                },
                {
                    "id": "event456",
                    "summary": "All Day Event",
                    "start": {"date": "2024-01-16"},
                    "end": {"date": "2024-01-17"},
                    "status": "confirmed",
                },
            ]
        }

    @pytest.fixture
    def sample_event(self) -> dict[str, Any]:
        """Sample single calendar event."""
        return {
            "id": "event123",
            "summary": "Team Meeting",
            "description": "Weekly team sync",
            "location": "Conference Room A",
            "htmlLink": "https://calendar.google.com/event?eid=event123",
            "start": {"dateTime": "2024-01-15T10:00:00+00:00"},
            "end": {"dateTime": "2024-01-15T11:00:00+00:00"},
            "status": "confirmed",
            "organizer": {
                "email": "organizer@example.com",
                "displayName": "Jane Doe",
            },
            "attendees": [
                {"email": "attendee1@example.com"},
                {"email": "attendee2@example.com"},
            ],
            "created": "2024-01-10T08:00:00.000Z",
            "updated": "2024-01-14T09:00:00.000Z",
        }

    def test_source_type(self, collector: GoogleCalendarCollector) -> None:
        """Test source_type property."""
        assert collector.source_type == SourceType.GOOGLE_CALENDAR

    def test_parse_event_time_datetime(self, collector: GoogleCalendarCollector) -> None:
        """Test parsing timed event."""
        time_info = {"dateTime": "2024-01-15T10:00:00+00:00"}
        result = collector._parse_event_time(time_info)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10

    def test_parse_event_time_date(self, collector: GoogleCalendarCollector) -> None:
        """Test parsing all-day event."""
        time_info = {"date": "2024-01-15"}
        result = collector._parse_event_time(time_info)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 0  # Midnight

    def test_parse_event_time_empty(self, collector: GoogleCalendarCollector) -> None:
        """Test parsing empty time info."""
        assert collector._parse_event_time({}) is None
        assert collector._parse_event_time(None) is None

    def test_parse_event_time_invalid(self, collector: GoogleCalendarCollector) -> None:
        """Test parsing invalid time."""
        assert collector._parse_event_time({"dateTime": "invalid"}) is None
        assert collector._parse_event_time({"date": "invalid"}) is None

    def test_parse_datetime(self, collector: GoogleCalendarCollector) -> None:
        """Test parsing ISO datetime strings."""
        # With Z suffix
        result1 = collector._parse_datetime("2024-01-15T10:00:00.000Z")
        assert result1 is not None
        assert result1.year == 2024

        # With offset
        result2 = collector._parse_datetime("2024-01-15T10:00:00+00:00")
        assert result2 is not None
        assert result2.year == 2024

        # None/invalid
        assert collector._parse_datetime(None) is None
        assert collector._parse_datetime("invalid") is None

    @pytest.mark.asyncio
    async def test_collect_success(
        self,
        collector: GoogleCalendarCollector,
        valid_credentials: dict[str, Any],
        sample_events_response: dict[str, Any],
    ) -> None:
        """Test successful collection."""
        mock_service = MagicMock()
        mock_events = MagicMock()

        # Setup chain: service.events()
        mock_service.events.return_value = mock_events

        # Mock list response
        mock_list = MagicMock()
        mock_list.execute.return_value = sample_events_response
        mock_events.list.return_value = mock_list

        with patch.object(collector, "_get_calendar_service", return_value=mock_service):
            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={"calendar_ids": ["primary"]},
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        assert len(items) == 2
        item = items[0]
        assert item.external_id == "event123"
        assert item.item_type == ItemType.EVENT
        assert item.title == "Team Meeting"
        assert item.content["location"] == "Conference Room A"
        assert item.content["attendee_count"] == 2

    @pytest.mark.asyncio
    async def test_collect_multiple_calendars(
        self,
        collector: GoogleCalendarCollector,
        valid_credentials: dict[str, Any],
        sample_events_response: dict[str, Any],
    ) -> None:
        """Test collection from multiple calendars."""
        mock_service = MagicMock()
        mock_events = MagicMock()

        mock_service.events.return_value = mock_events

        mock_list = MagicMock()
        mock_list.execute.return_value = sample_events_response
        mock_events.list.return_value = mock_list

        with patch.object(collector, "_get_calendar_service", return_value=mock_service):
            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={"calendar_ids": ["primary", "work@example.com"]},
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        # Each calendar returns 2 events
        assert len(items) == 4

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self,
        collector: GoogleCalendarCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation success."""
        mock_service = MagicMock()
        mock_calendar_list = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": []}

        mock_service.calendarList.return_value = mock_calendar_list
        mock_calendar_list.list.return_value = mock_list

        with patch.object(collector, "_get_calendar_service", return_value=mock_service):
            result = await collector.validate_credentials(valid_credentials)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_credentials_failure(
        self,
        collector: GoogleCalendarCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation failure."""
        with patch.object(collector, "_get_calendar_service", return_value=None):
            result = await collector.validate_credentials(valid_credentials)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_credentials_missing(
        self,
        collector: GoogleCalendarCollector,
    ) -> None:
        """Test credential validation with missing credentials."""
        with patch.object(collector, "_get_calendar_service", return_value=None):
            result = await collector.validate_credentials({})

        assert result is False

    def test_event_to_digest_item(
        self,
        collector: GoogleCalendarCollector,
        sample_event: dict[str, Any],
    ) -> None:
        """Test event to DigestItem conversion."""
        source_id = str(uuid4())
        item = collector._event_to_digest_item(source_id, "primary", sample_event)

        assert item.source_id == UUID(source_id)
        assert item.external_id == "event123"
        assert item.item_type == ItemType.EVENT
        assert item.title == "Team Meeting"
        assert item.content["summary"] == "Team Meeting"
        assert item.content["description"] == "Weekly team sync"
        assert item.content["location"] == "Conference Room A"
        assert item.content["calendar_id"] == "primary"
        assert item.content["organizer"] == "Jane Doe"
        assert item.content["attendee_count"] == 2
        assert "attendee1@example.com" in item.content["attendees"]
        assert item.content["is_all_day"] is False
        assert item.external_url == "https://calendar.google.com/event?eid=event123"
        assert item.metadata["status"] == "confirmed"

    def test_event_to_digest_item_all_day(
        self,
        collector: GoogleCalendarCollector,
    ) -> None:
        """Test all-day event conversion."""
        source_id = str(uuid4())
        event = {
            "id": "event789",
            "summary": "Holiday",
            "start": {"date": "2024-01-15"},
            "end": {"date": "2024-01-16"},
            "status": "confirmed",
        }

        item = collector._event_to_digest_item(source_id, "primary", event)

        assert item.content["is_all_day"] is True
        assert item.metadata["is_all_day"] is True

    def test_event_to_digest_item_no_title(
        self,
        collector: GoogleCalendarCollector,
    ) -> None:
        """Test event without title."""
        source_id = str(uuid4())
        event = {
            "id": "event789",
            "start": {"dateTime": "2024-01-15T10:00:00+00:00"},
            "end": {"dateTime": "2024-01-15T11:00:00+00:00"},
        }

        item = collector._event_to_digest_item(source_id, "primary", event)

        assert item.title == "(No title)"

    def test_event_to_digest_item_recurring(
        self,
        collector: GoogleCalendarCollector,
    ) -> None:
        """Test recurring event detection."""
        source_id = str(uuid4())
        event = {
            "id": "event789",
            "summary": "Recurring",
            "recurringEventId": "parent123",
            "start": {"dateTime": "2024-01-15T10:00:00+00:00"},
            "end": {"dateTime": "2024-01-15T11:00:00+00:00"},
        }

        item = collector._event_to_digest_item(source_id, "primary", event)

        assert item.content["recurring"] is True
