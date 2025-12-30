"""Outlook Mail collector implementation using Microsoft Graph API."""

from datetime import datetime
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


@CollectorRegistry.register(SourceType.OUTLOOK_MAIL)
class OutlookMailCollector(BaseCollector):
    """Collector for Outlook/Microsoft 365 emails.

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
            "folders": ["inbox"],  # Folder names to fetch from
            "max_results": 50,
            "filter": "isRead eq false"  # Optional OData filter
        }
    """

    @property
    def source_type(self) -> SourceType:
        """Return the source type for this collector."""
        return SourceType.OUTLOOK_MAIL

    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect emails from Outlook.

        Args:
            source_id: ID of the source.
            credentials: Microsoft Graph OAuth2 credentials.
            config: Collection config (folders, max_results, filter).
            since: Fetch emails received since this time.

        Returns:
            List of DigestItems representing emails.

        """
        log = logger.bind(source_id=source_id)
        log.info("Starting Outlook Mail collection")

        access_token = credentials.get("access_token", "")
        if not access_token:
            err_msg = "Missing Outlook access token"
            raise AuthenticationError(err_msg)

        folders = config.get("folders", ["inbox"])
        max_results = config.get("max_results", 50)
        custom_filter = config.get("filter", "")

        since_dt = self.get_since_datetime(since)

        log.debug(
            "Fetching emails",
            folders=folders,
            since=since_dt.isoformat(),
        )

        items: list[DigestItem] = []
        client = await self.get_client()

        try:
            for folder in folders:
                messages = await self._fetch_messages(
                    client,
                    access_token,
                    folder,
                    since_dt,
                    max_results,
                    custom_filter,
                )

                for msg in messages:
                    item = self._message_to_digest_item(source_id, folder, msg)
                    items.append(item)

            log.info("Outlook Mail collection completed", email_count=len(items))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                err_msg = "Outlook token invalid or expired"
                raise AuthenticationError(err_msg) from e
            err_msg = f"Microsoft Graph API error: {e}"
            raise CollectorError(
                err_msg,
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
            logger.debug("Outlook Mail credential validation failed", error=str(e))

        return valid

    async def _fetch_messages(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        folder: str,
        since: datetime,
        limit: int,
        custom_filter: str,
    ) -> list[dict[str, Any]]:
        """Fetch messages from a folder.

        Args:
            client: HTTP client.
            access_token: Microsoft Graph access token.
            folder: Folder name (e.g., "inbox").
            since: Fetch messages after this time.
            limit: Maximum messages to fetch.
            custom_filter: Optional OData filter.

        Returns:
            List of message dictionaries.

        """
        messages: list[dict[str, Any]] = []

        # Build filter
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        date_filter = f"receivedDateTime ge {since_str}"
        odata_filter = f"{date_filter} and {custom_filter}" if custom_filter else date_filter

        # Build URL
        url = f"{GRAPH_API_BASE}/me/mailFolders/{folder}/messages"
        params: dict[str, str | int] = {
            "$filter": odata_filter,
            "$orderby": "receivedDateTime desc",
            "$top": min(limit, 100),
            "$select": (
                "id,subject,from,toRecipients,receivedDateTime,"
                "bodyPreview,isRead,hasAttachments,webLink,importance,"
                "flag,categories"
            ),
        }

        next_link: str | None = url

        while next_link and len(messages) < limit:
            # Use next_link for pagination, otherwise use url with params
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
                    "Failed to fetch messages",
                    folder=folder,
                    status=response.status_code,
                )
                break

            data = response.json()
            batch = data.get("value", [])
            messages.extend(batch)

            # Check for pagination
            next_link = data.get("@odata.nextLink")
            if not batch:
                break

        return messages[:limit]

    def _message_to_digest_item(
        self,
        source_id: str,
        folder: str,
        message: dict[str, Any],
    ) -> DigestItem:
        """Convert Outlook message to DigestItem.

        Args:
            source_id: ID of the source.
            folder: Folder name.
            message: Microsoft Graph message dictionary.

        Returns:
            DigestItem representing the email.

        """
        msg_id = message.get("id", "")
        subject = message.get("subject", "(No Subject)")
        body_preview = message.get("bodyPreview", "")
        is_read = message.get("isRead", False)
        has_attachments = message.get("hasAttachments", False)
        web_link = message.get("webLink", "")
        importance = message.get("importance", "normal")
        categories = message.get("categories", [])

        # Parse sender
        from_info = message.get("from", {})
        email_address = from_info.get("emailAddress", {})
        sender_name = email_address.get("name", "")
        sender_email = email_address.get("address", "")
        sender = f"{sender_name} <{sender_email}>" if sender_name else sender_email

        # Parse recipients
        to_recipients = message.get("toRecipients", [])
        to_emails = [
            r.get("emailAddress", {}).get("address", "")
            for r in to_recipients
            if r.get("emailAddress", {}).get("address")
        ]

        # Parse dates
        received_str = message.get("receivedDateTime", "")
        received_at = self._parse_graph_datetime(received_str)

        # Parse flag
        flag_info = message.get("flag", {})
        flag_status = flag_info.get("flagStatus", "notFlagged")
        is_flagged = flag_status == "flagged"

        # Build content
        content = {
            "message_id": msg_id,
            "folder": folder,
            "subject": subject,
            "sender": sender,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "to": to_emails,
            "body_preview": body_preview,
            "is_read": is_read,
            "has_attachments": has_attachments,
            "importance": importance,
            "is_flagged": is_flagged,
            "categories": categories,
        }

        # Metadata
        metadata = {
            "sender": sender_name or sender_email,
            "is_read": is_read,
            "importance": importance,
            "is_flagged": is_flagged,
        }

        return self.create_digest_item(
            source_id=source_id,
            external_id=msg_id,
            item_type=ItemType.EMAIL,
            title=subject,
            content=content,
            metadata=metadata,
            external_url=web_link,
            external_created_at=received_at,
            external_updated_at=received_at,
        )

    @staticmethod
    def _parse_graph_datetime(dt_str: str | None) -> datetime | None:
        """Parse Microsoft Graph datetime string.

        Args:
            dt_str: ISO format datetime string.

        Returns:
            Parsed datetime or None.

        """
        if not dt_str:
            return None

        try:
            # Graph API returns ISO format: "2024-01-15T10:30:00Z"
            return datetime.fromisoformat(dt_str)
        except ValueError:
            return None
