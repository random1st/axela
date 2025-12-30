"""Outlook Calendar collector implementation using Microsoft Graph API."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from axela.application.ports.collector import (
    AuthenticationError,
    CollectorError,
)
from axela.domain.enums import ItemType, SourceType
from axela.domain.models import DigestItem

from .base import BaseCollector, CollectorRegistry

logger = structlog.get_logger()

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


@CollectorRegistry.register(SourceType.OUTLOOK_CALENDAR)
class OutlookCalendarCollector(BaseCollector):
    """Collector for Outlook/Microsoft 365 calendar events.

    Uses Microsoft Graph API with OAuth2 access token.

    Credentials format:
        {
            "access_token": "eyJ...",
            "refresh_token": "0.A...",
            "client_id": "...",
            "client_secret": "...",
            "tenant_id": "..."
        }

    Config format:
        {
            "calendar_ids": ["primary"],  # Calendar IDs (or "primary" for default)
            "max_results": 50,
            "days_ahead": 7  # How many days ahead to look for events
        }
    """

    @property
    def source_type(self) -> SourceType:
        """Return the source type for this collector."""
        return SourceType.OUTLOOK_CALENDAR

    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect events from Outlook Calendar.

        Args:
            source_id: ID of the source.
            credentials: Microsoft Graph OAuth2 credentials.
            config: Collection config (calendar_ids, max_results, days_ahead).
            since: Fetch events after this time.

        Returns:
            List of DigestItems representing calendar events.

        """
        log = logger.bind(source_id=source_id)
        log.info("Starting Outlook Calendar collection")

        access_token = credentials.get("access_token", "")
        if not access_token:
            msg = "Missing Outlook access token"
            raise AuthenticationError(msg)

        calendar_ids = config.get("calendar_ids", ["primary"])
        max_results = config.get("max_results", 50)
        days_ahead = config.get("days_ahead", 7)

        since_dt = self.get_since_datetime(since)
        end_dt = datetime.now(UTC) + timedelta(days=days_ahead)

        log.debug(
            "Fetching events",
            calendar_ids=calendar_ids,
            start=since_dt.isoformat(),
            end=end_dt.isoformat(),
        )

        items: list[DigestItem] = []
        client = await self.get_client()

        try:
            for calendar_id in calendar_ids:
                events = await self._fetch_events(
                    client,
                    access_token,
                    calendar_id,
                    since_dt,
                    end_dt,
                    max_results,
                )

                for event in events:
                    item = self._event_to_digest_item(source_id, calendar_id, event)
                    items.append(item)

            log.info("Outlook Calendar collection completed", event_count=len(items))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                msg = "Outlook token invalid or expired"
                raise AuthenticationError(msg) from e
            msg = f"Microsoft Graph API error: {e}"
            raise CollectorError(
                msg,
                error_type="graph_api",
                recoverable=e.response.status_code >= 500,
            ) from e

        return items

    async def validate_credentials(
        self,
        credentials: dict[str, Any],
    ) -> bool:
        """Validate Outlook credentials by fetching user profile.

        Args:
            credentials: Microsoft Graph OAuth2 credentials to validate.

        Returns:
            True if credentials are valid.

        """
        access_token = credentials.get("access_token", "")
        if not access_token:
            return False

        client = await self.get_client()

        valid = False
        try:
            response = await client.get(
                f"{GRAPH_API_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            valid = response.is_success
        except Exception as e:
            logger.debug("Outlook Calendar credential validation failed", error=str(e))

        return valid

    async def _fetch_events(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        calendar_id: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch events from a calendar.

        Args:
            client: HTTP client.
            access_token: Microsoft Graph access token.
            calendar_id: Calendar ID or "primary".
            start: Start of time range.
            end: End of time range.
            limit: Maximum events to fetch.

        Returns:
            List of event dictionaries.

        """
        events: list[dict[str, Any]] = []

        # Build URL - use calendarView for time range queries
        if calendar_id == "primary":
            url = f"{GRAPH_API_BASE}/me/calendarView"
        else:
            url = f"{GRAPH_API_BASE}/me/calendars/{calendar_id}/calendarView"

        start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        params: dict[str, str | int] = {
            "startDateTime": start_str,
            "endDateTime": end_str,
            "$top": min(limit, 100),
            "$orderby": "start/dateTime",
            "$select": (
                "id,subject,body,start,end,location,organizer,attendees,"
                "webLink,isAllDay,isCancelled,showAs,importance,isOnlineMeeting,"
                "onlineMeetingUrl,recurrence"
            ),
        }

        next_link: str | None = url

        while next_link and len(events) < limit:
            if next_link != url:
                response = await client.get(
                    next_link,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            else:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )

            if not response.is_success:
                logger.warning(
                    "Failed to fetch events",
                    calendar_id=calendar_id,
                    status=response.status_code,
                )
                break

            data = response.json()
            batch = data.get("value", [])
            events.extend(batch)

            next_link = data.get("@odata.nextLink")
            if not batch:
                break

        return events[:limit]

    def _event_to_digest_item(
        self,
        source_id: str,
        calendar_id: str,
        event: dict[str, Any],
    ) -> DigestItem:
        """Convert Outlook event to DigestItem.

        Args:
            source_id: ID of the source.
            calendar_id: Calendar ID.
            event: Microsoft Graph event dictionary.

        Returns:
            DigestItem representing the event.

        """
        event_id = event.get("id", "")
        subject = event.get("subject", "(No title)")
        body_info = event.get("body", {})
        body_preview = body_info.get("content", "")[:200] if body_info else ""
        web_link = event.get("webLink", "")
        is_all_day = event.get("isAllDay", False)
        is_cancelled = event.get("isCancelled", False)
        show_as = event.get("showAs", "busy")
        importance = event.get("importance", "normal")
        is_online = event.get("isOnlineMeeting", False)
        online_url = event.get("onlineMeetingUrl", "")
        is_recurring = event.get("recurrence") is not None

        # Parse location
        location_info = event.get("location", {})
        location = location_info.get("displayName", "")

        # Parse organizer
        organizer_info = event.get("organizer", {})
        organizer_email = organizer_info.get("emailAddress", {})
        organizer_name = organizer_email.get("name", "")
        organizer_address = organizer_email.get("address", "")

        # Parse attendees
        attendees = event.get("attendees", [])
        attendee_emails = [
            a.get("emailAddress", {}).get("address", "") for a in attendees if a.get("emailAddress", {}).get("address")
        ]
        attendee_count = len(attendees)

        # Parse start/end times
        start_info = event.get("start", {})
        end_info = event.get("end", {})
        start_dt = self._parse_event_time(start_info)
        end_dt = self._parse_event_time(end_info)

        # Build content
        content = {
            "event_id": event_id,
            "calendar_id": calendar_id,
            "subject": subject,
            "body_preview": body_preview,
            "location": location,
            "start": start_dt.isoformat() if start_dt else None,
            "end": end_dt.isoformat() if end_dt else None,
            "is_all_day": is_all_day,
            "is_cancelled": is_cancelled,
            "organizer": organizer_name,
            "organizer_email": organizer_address,
            "attendees": attendee_emails[:10],
            "attendee_count": attendee_count,
            "show_as": show_as,
            "importance": importance,
            "is_online_meeting": is_online,
            "online_meeting_url": online_url,
            "is_recurring": is_recurring,
        }

        # Metadata
        metadata = {
            "start": start_dt.isoformat() if start_dt else None,
            "is_all_day": is_all_day,
            "location": location,
            "attendees": attendee_count,
            "show_as": show_as,
            "is_online": is_online,
        }

        return self.create_digest_item(
            source_id=source_id,
            external_id=event_id,
            item_type=ItemType.EVENT,
            title=subject,
            content=content,
            metadata=metadata,
            external_url=web_link,
            external_created_at=start_dt,
            external_updated_at=start_dt,
        )

    @staticmethod
    def _parse_event_time(time_info: dict[str, Any] | None) -> datetime | None:
        """Parse event start/end time.

        Args:
            time_info: Time info dict with 'dateTime' and 'timeZone', or None.

        Returns:
            Parsed datetime or None.

        """
        if not time_info:
            return None

        date_time_str = time_info.get("dateTime")
        if not date_time_str:
            return None

        result: datetime | None = None
        try:
            # Graph API returns: "2024-01-15T10:00:00.0000000"
            # Truncate the fractional seconds for parsing
            if "." in date_time_str:
                date_time_str = date_time_str.split(".")[0]

            dt = datetime.fromisoformat(date_time_str)

            # If no timezone info, assume UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)

            result = dt
        except ValueError as e:
            logger.debug("Failed to parse event datetime", datetime_str=date_time_str, error=str(e))

        return result
