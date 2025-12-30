"""Tests for Outlook Calendar collector."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from axela.domain.enums import ItemType, SourceType
from axela.infrastructure.collectors.outlook_calendar import OutlookCalendarCollector


class TestOutlookCalendarCollector:
    """Tests for OutlookCalendarCollector."""

    @pytest.fixture
    def collector(self) -> OutlookCalendarCollector:
        """Create an OutlookCalendarCollector instance."""
        return OutlookCalendarCollector()

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
    def sample_events_response(self) -> dict[str, Any]:
        """Sample Microsoft Graph events response."""
        return {
            "value": [
                {
                    "id": "AAMkAGI2Event1AAA=",
                    "subject": "Team Standup",
                    "body": {"content": "Daily standup meeting"},
                    "start": {
                        "dateTime": "2024-01-15T09:00:00.0000000",
                        "timeZone": "UTC",
                    },
                    "end": {
                        "dateTime": "2024-01-15T09:30:00.0000000",
                        "timeZone": "UTC",
                    },
                    "location": {"displayName": "Conference Room A"},
                    "organizer": {
                        "emailAddress": {
                            "name": "John Manager",
                            "address": "john.manager@example.com",
                        }
                    },
                    "attendees": [
                        {"emailAddress": {"address": "dev1@example.com"}},
                        {"emailAddress": {"address": "dev2@example.com"}},
                    ],
                    "webLink": "https://outlook.office365.com/calendar/item/...",
                    "isAllDay": False,
                    "isCancelled": False,
                    "showAs": "busy",
                    "importance": "normal",
                    "isOnlineMeeting": True,
                    "onlineMeetingUrl": "https://teams.microsoft.com/l/...",
                },
                {
                    "id": "AAMkAGI2Event2AAA=",
                    "subject": "All Day Planning",
                    "start": {"dateTime": "2024-01-16", "timeZone": "UTC"},
                    "end": {"dateTime": "2024-01-17", "timeZone": "UTC"},
                    "isAllDay": True,
                    "isCancelled": False,
                    "showAs": "free",
                    "recurrence": {"pattern": {"type": "weekly"}},
                },
            ]
        }

    @pytest.fixture
    def sample_event(self) -> dict[str, Any]:
        """Single sample event."""
        return {
            "id": "AAMkAGI2Event1AAA=",
            "subject": "Important Meeting",
            "body": {"content": "Quarterly review"},
            "start": {"dateTime": "2024-01-15T10:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2024-01-15T11:00:00.0000000", "timeZone": "UTC"},
            "location": {"displayName": "Board Room"},
            "organizer": {
                "emailAddress": {
                    "name": "CEO",
                    "address": "ceo@example.com",
                }
            },
            "attendees": [
                {"emailAddress": {"address": "cto@example.com"}},
                {"emailAddress": {"address": "cfo@example.com"}},
            ],
            "webLink": "https://outlook.office365.com/calendar/item/test",
            "isAllDay": False,
            "isCancelled": False,
            "showAs": "busy",
            "importance": "high",
            "isOnlineMeeting": True,
            "onlineMeetingUrl": "https://teams.microsoft.com/l/test",
        }

    def test_source_type(self, collector: OutlookCalendarCollector) -> None:
        """Test source_type property."""
        assert collector.source_type == SourceType.OUTLOOK_CALENDAR

    def test_parse_event_time(self, collector: OutlookCalendarCollector) -> None:
        """Test event time parsing."""
        time_info = {"dateTime": "2024-01-15T10:00:00.0000000", "timeZone": "UTC"}
        result = collector._parse_event_time(time_info)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10

    def test_parse_event_time_without_fraction(self, collector: OutlookCalendarCollector) -> None:
        """Test parsing time without fractional seconds."""
        time_info = {"dateTime": "2024-01-15T10:00:00", "timeZone": "UTC"}
        result = collector._parse_event_time(time_info)

        assert result is not None
        assert result.year == 2024

    def test_parse_event_time_empty(self, collector: OutlookCalendarCollector) -> None:
        """Test parsing empty time info."""
        assert collector._parse_event_time({}) is None
        assert collector._parse_event_time(None) is None

    def test_parse_event_time_invalid(self, collector: OutlookCalendarCollector) -> None:
        """Test parsing invalid time."""
        assert collector._parse_event_time({"dateTime": "invalid"}) is None

    @pytest.mark.asyncio
    async def test_collect_success(
        self,
        collector: OutlookCalendarCollector,
        valid_credentials: dict[str, Any],
        sample_events_response: dict[str, Any],
    ) -> None:
        """Test successful collection."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = sample_events_response
        mock_client.get.return_value = mock_response

        with pytest.MonkeyPatch.context() as m:
            m.setattr(collector, "get_client", AsyncMock(return_value=mock_client))

            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={"calendar_ids": ["primary"]},
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        assert len(items) == 2
        item = items[0]
        assert item.external_id == "AAMkAGI2Event1AAA="
        assert item.item_type == ItemType.EVENT
        assert item.title == "Team Standup"
        assert item.content["location"] == "Conference Room A"
        assert item.content["is_online_meeting"] is True

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self,
        collector: OutlookCalendarCollector,
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
        collector: OutlookCalendarCollector,
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
        collector: OutlookCalendarCollector,
    ) -> None:
        """Test credential validation with missing token."""
        result = await collector.validate_credentials({})
        assert result is False

    def test_event_to_digest_item(
        self,
        collector: OutlookCalendarCollector,
        sample_event: dict[str, Any],
    ) -> None:
        """Test event to DigestItem conversion."""
        source_id = str(uuid4())
        item = collector._event_to_digest_item(source_id, "primary", sample_event)

        assert item.source_id == UUID(source_id)
        assert item.external_id == "AAMkAGI2Event1AAA="
        assert item.item_type == ItemType.EVENT
        assert item.title == "Important Meeting"
        assert item.content["calendar_id"] == "primary"
        assert item.content["location"] == "Board Room"
        assert item.content["organizer"] == "CEO"
        assert item.content["attendee_count"] == 2
        assert item.content["is_all_day"] is False
        assert item.content["is_online_meeting"] is True
        assert item.content["importance"] == "high"
        assert "cto@example.com" in item.content["attendees"]
        assert item.metadata["show_as"] == "busy"
        assert item.metadata["is_online"] is True

    def test_event_to_digest_item_all_day(
        self,
        collector: OutlookCalendarCollector,
    ) -> None:
        """Test all-day event conversion."""
        source_id = str(uuid4())
        event = {
            "id": "event123",
            "subject": "Holiday",
            "start": {"dateTime": "2024-01-15"},
            "end": {"dateTime": "2024-01-16"},
            "isAllDay": True,
            "isCancelled": False,
            "showAs": "oof",
        }

        item = collector._event_to_digest_item(source_id, "primary", event)

        assert item.content["is_all_day"] is True
        assert item.metadata["is_all_day"] is True

    def test_event_to_digest_item_recurring(
        self,
        collector: OutlookCalendarCollector,
    ) -> None:
        """Test recurring event detection."""
        source_id = str(uuid4())
        event = {
            "id": "event123",
            "subject": "Weekly Sync",
            "start": {"dateTime": "2024-01-15T10:00:00"},
            "end": {"dateTime": "2024-01-15T11:00:00"},
            "isAllDay": False,
            "isCancelled": False,
            "recurrence": {"pattern": {"type": "weekly", "daysOfWeek": ["monday"]}},
        }

        item = collector._event_to_digest_item(source_id, "primary", event)

        assert item.content["is_recurring"] is True

    def test_event_to_digest_item_cancelled(
        self,
        collector: OutlookCalendarCollector,
    ) -> None:
        """Test cancelled event."""
        source_id = str(uuid4())
        event = {
            "id": "event123",
            "subject": "Cancelled Meeting",
            "start": {"dateTime": "2024-01-15T10:00:00"},
            "end": {"dateTime": "2024-01-15T11:00:00"},
            "isAllDay": False,
            "isCancelled": True,
        }

        item = collector._event_to_digest_item(source_id, "primary", event)

        assert item.content["is_cancelled"] is True
