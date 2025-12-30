"""Google Calendar collector implementation."""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from axela.application.ports.collector import (
    AuthenticationError,
    CollectorError,
    ConfigurationError,
)
from axela.domain.enums import ItemType, SourceType
from axela.domain.models import DigestItem

from .base import BaseCollector, CollectorRegistry

logger = structlog.get_logger()

# Type-erased references to untyped Google auth classes (avoids mypy no-untyped-call)
_Credentials: Any = Credentials
_Request: Any = Request

# Google Calendar API scope for read-only access
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


@CollectorRegistry.register(SourceType.GOOGLE_CALENDAR)
class GoogleCalendarCollector(BaseCollector):
    """Collector for Google Calendar events.

    Uses Google Calendar API with OAuth2 credentials.

    Credentials format:
        {
            "access_token": "ya29...",
            "refresh_token": "1//...",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "xxx.apps.googleusercontent.com",
            "client_secret": "xxx",
            "scopes": ["https://www.googleapis.com/auth/calendar.readonly"]
        }

    Config format:
        {
            "calendar_ids": ["primary"],  # Calendar IDs to fetch from
            "max_results": 50,
            "days_ahead": 7  # How many days ahead to look for events
        }
    """

    @property
    def source_type(self) -> SourceType:
        """Return the source type for this collector."""
        return SourceType.GOOGLE_CALENDAR

    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect events from Google Calendar.

        Args:
            source_id: ID of the source.
            credentials: Google OAuth2 credentials.
            config: Collection config (calendar_ids, max_results, days_ahead).
            since: Fetch events updated since this time.

        Returns:
            List of DigestItems representing calendar events.

        """
        log = logger.bind(source_id=source_id)
        log.info("Starting Google Calendar collection")

        # Get Calendar service
        service = self._get_calendar_service(credentials)
        if service is None:
            msg = "Failed to authenticate with Google Calendar"
            raise AuthenticationError(msg)

        # Config
        calendar_ids = config.get("calendar_ids", ["primary"])
        max_results = config.get("max_results", 50)
        days_ahead = config.get("days_ahead", 7)

        # Time bounds
        since_dt = self.get_since_datetime(since)
        time_min = since_dt.isoformat()
        time_max = (datetime.now(UTC) + timedelta(days=days_ahead)).isoformat()

        log.debug(
            "Fetching events",
            calendar_ids=calendar_ids,
            time_min=time_min,
            time_max=time_max,
        )

        items: list[DigestItem] = []
        try:
            for calendar_id in calendar_ids:
                events = self._list_events(
                    service,
                    calendar_id,
                    time_min,
                    time_max,
                    max_results,
                )

                for event in events:
                    item = self._event_to_digest_item(source_id, calendar_id, event)
                    items.append(item)

            log.info("Google Calendar collection completed", event_count=len(items))

        except HttpError as e:
            if e.resp.status == 401:
                msg = "Google Calendar credentials expired or revoked"
                raise AuthenticationError(msg) from e
            msg = f"Google Calendar API error: {e}"
            raise CollectorError(
                msg,
                error_type="calendar_api",
                recoverable=e.resp.status >= 500,
            ) from e

        return items

    async def validate_credentials(
        self,
        credentials: dict[str, Any],
    ) -> bool:
        """Validate Google Calendar credentials by listing calendars.

        Args:
            credentials: Google OAuth2 credentials to validate.

        Returns:
            True if credentials are valid.

        """
        service = self._get_calendar_service(credentials)
        if service is None:
            return False

        valid = False
        try:
            # Try to list calendars
            service.calendarList().list(maxResults=1).execute()
            valid = True
        except HttpError as e:
            logger.debug("Google Calendar credential validation failed", error=str(e))

        return valid

    def _get_calendar_service(self, credentials: dict[str, Any]) -> Any | None:
        """Create Google Calendar API service from credentials.

        Args:
            credentials: OAuth2 credentials dictionary.

        Returns:
            Calendar API service or None if authentication fails.

        """
        # Validate required fields before try block
        required = [
            "access_token",
            "refresh_token",
            "token_uri",
            "client_id",
            "client_secret",
        ]
        self._validate_credentials_fields(credentials, required)

        try:
            # Create credentials object
            creds = _Credentials(
                token=credentials["access_token"],
                refresh_token=credentials["refresh_token"],
                token_uri=credentials["token_uri"],
                client_id=credentials["client_id"],
                client_secret=credentials["client_secret"],
                scopes=credentials.get("scopes", CALENDAR_SCOPES),
            )

            # Refresh if expired
            if creds.expired and creds.refresh_token:
                creds.refresh(_Request())

            # Build service
            return build("calendar", "v3", credentials=creds, cache_discovery=False)

        except Exception as e:
            logger.exception("Failed to create Calendar service", error=str(e))
            return None

    @staticmethod
    def _validate_credentials_fields(credentials: dict[str, Any], required: list[str]) -> None:
        """Validate required credential fields are present.

        Args:
            credentials: Credentials dictionary.
            required: List of required field names.

        Raises:
            ConfigurationError: If required fields are missing.

        """
        if not all(credentials.get(k) for k in required):
            msg = f"Missing required credentials: {required}"
            raise ConfigurationError(msg)

    def _list_events(
        self,
        service: Any,
        calendar_id: str,
        time_min: str,
        time_max: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """List events from a calendar.

        Args:
            service: Calendar API service.
            calendar_id: Calendar ID to fetch from.
            time_min: Start time (ISO format).
            time_max: End time (ISO format).
            max_results: Maximum results to return.

        Returns:
            List of event dictionaries.

        """
        events: list[dict[str, Any]] = []
        page_token = None

        while len(events) < max_results:
            remaining = max_results - len(events)
            result: dict[str, Any] = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=min(remaining, 250),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )

            batch = result.get("items", [])
            events.extend(batch)

            page_token = result.get("nextPageToken")
            if not page_token or not batch:
                break

        return events[:max_results]

    def _event_to_digest_item(
        self,
        source_id: str,
        calendar_id: str,
        event: dict[str, Any],
    ) -> DigestItem:
        """Convert Calendar event to DigestItem.

        Args:
            source_id: ID of the source.
            calendar_id: Calendar ID the event came from.
            event: Google Calendar event dictionary.

        Returns:
            DigestItem representing the event.

        """
        event_id = event.get("id", "")
        summary = event.get("summary", "(No title)")
        description = event.get("description", "")
        location = event.get("location", "")
        html_link = event.get("htmlLink", "")

        # Parse start/end times
        start_info = event.get("start", {})
        end_info = event.get("end", {})
        is_all_day = "date" in start_info

        start_dt = self._parse_event_time(start_info)
        end_dt = self._parse_event_time(end_info)

        # Get attendees
        attendees = event.get("attendees", [])
        attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]
        attendee_count = len(attendees)

        # Get organizer
        organizer = event.get("organizer", {})
        organizer_email = organizer.get("email", "")
        organizer_name = organizer.get("displayName", organizer_email)

        # Get status
        status = event.get("status", "confirmed")

        # Get recurrence info
        recurring = "recurringEventId" in event

        # Created/updated times
        created_at = self._parse_datetime(event.get("created"))
        updated_at = self._parse_datetime(event.get("updated"))

        # Build content
        content = {
            "event_id": event_id,
            "calendar_id": calendar_id,
            "summary": summary,
            "description": description,
            "location": location,
            "start": start_dt.isoformat() if start_dt else None,
            "end": end_dt.isoformat() if end_dt else None,
            "is_all_day": is_all_day,
            "organizer": organizer_name,
            "organizer_email": organizer_email,
            "attendees": attendee_emails[:10],  # Limit for storage
            "attendee_count": attendee_count,
            "status": status,
            "recurring": recurring,
        }

        # Metadata for quick display
        metadata = {
            "start": start_dt.isoformat() if start_dt else None,
            "is_all_day": is_all_day,
            "location": location,
            "attendees": attendee_count,
            "status": status,
        }

        return self.create_digest_item(
            source_id=source_id,
            external_id=event_id,
            item_type=ItemType.EVENT,
            title=summary,
            content=content,
            metadata=metadata,
            external_url=html_link,
            external_created_at=created_at,
            external_updated_at=updated_at,
        )

    @staticmethod
    def _parse_event_time(time_info: dict[str, Any] | None) -> datetime | None:
        """Parse event start/end time.

        Args:
            time_info: Time info dict with 'dateTime' or 'date' field, or None.

        Returns:
            Parsed datetime or None.

        """
        if not time_info:
            return None

        # All-day events have 'date', timed events have 'dateTime'
        if "dateTime" in time_info:
            try:
                return datetime.fromisoformat(time_info["dateTime"])
            except ValueError:
                return None
        elif "date" in time_info:
            try:
                # All-day event: parse date as midnight UTC
                return datetime.strptime(time_info["date"], "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                return None

        return None

    @staticmethod
    def _parse_datetime(dt_str: str | None) -> datetime | None:
        """Parse ISO datetime string.

        Args:
            dt_str: ISO format datetime string.

        Returns:
            Parsed datetime or None.

        """
        if not dt_str:
            return None

        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            return None
