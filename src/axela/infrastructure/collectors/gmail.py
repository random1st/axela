"""Gmail collector implementation."""

import base64
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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

# Gmail API scope for read-only access
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@CollectorRegistry.register(SourceType.GMAIL)
class GmailCollector(BaseCollector):
    """Collector for Gmail emails.

    Uses Gmail API with OAuth2 credentials.

    Credentials format:
        {
            "access_token": "ya29...",
            "refresh_token": "1//...",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "xxx.apps.googleusercontent.com",
            "client_secret": "xxx",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]
        }

    Config format:
        {
            "query": "is:unread",  # Gmail search query
            "max_results": 50,
            "labels": ["INBOX"]  # Optional label filter
        }
    """

    @property
    def source_type(self) -> SourceType:
        """Return the source type for this collector."""
        return SourceType.GMAIL

    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect emails from Gmail.

        Args:
            source_id: ID of the source.
            credentials: Gmail OAuth2 credentials.
            config: Collection config (query, max_results, labels).
            since: Fetch emails received since this time.

        Returns:
            List of DigestItems representing emails.

        """
        log = logger.bind(source_id=source_id)
        log.info("Starting Gmail collection")

        # Get Gmail service
        service = self._get_gmail_service(credentials)
        if service is None:
            err_msg = "Failed to authenticate with Gmail"
            raise AuthenticationError(err_msg)

        # Build query
        since_dt = self.get_since_datetime(since)
        query = self._build_query(config, since_dt)
        max_results = config.get("max_results", 50)
        labels = config.get("labels", ["INBOX"])

        log.debug("Fetching emails", query=query, max_results=max_results)

        items: list[DigestItem] = []
        try:
            # Fetch message list
            messages = self._list_messages(service, query, labels, max_results)

            # Fetch full message details
            for msg_info in messages:
                msg = self._get_message(service, msg_info["id"])
                if msg:
                    item = self._message_to_digest_item(source_id, msg)
                    items.append(item)

            log.info("Gmail collection completed", email_count=len(items))

        except HttpError as e:
            if e.resp.status == 401:
                err_msg = "Gmail credentials expired or revoked"
                raise AuthenticationError(err_msg) from e
            err_msg = f"Gmail API error: {e}"
            raise CollectorError(
                err_msg,
                error_type="gmail_api",
                recoverable=e.resp.status >= 500,
            ) from e

        return items

    async def validate_credentials(
        self,
        credentials: dict[str, Any],
    ) -> bool:
        """Validate Gmail credentials by fetching user profile.

        Args:
            credentials: Gmail OAuth2 credentials to validate.

        Returns:
            True if credentials are valid.

        """
        service = self._get_gmail_service(credentials)
        if service is None:
            return False

        valid = False
        try:
            # Try to get user profile
            service.users().getProfile(userId="me").execute()
            valid = True
        except HttpError as e:
            logger.debug("Gmail credential validation failed", error=str(e))

        return valid

    def _get_gmail_service(self, credentials: dict[str, Any]) -> Any | None:
        """Create Gmail API service from credentials.

        Args:
            credentials: OAuth2 credentials dictionary.

        Returns:
            Gmail API service or None if authentication fails.

        """
        # Validate required fields before try block
        required = ["access_token", "refresh_token", "token_uri", "client_id", "client_secret"]
        self._validate_credentials_fields(credentials, required)

        try:
            # Create credentials object
            creds = _Credentials(
                token=credentials["access_token"],
                refresh_token=credentials["refresh_token"],
                token_uri=credentials["token_uri"],
                client_id=credentials["client_id"],
                client_secret=credentials["client_secret"],
                scopes=credentials.get("scopes", GMAIL_SCOPES),
            )

            # Refresh if expired
            if creds.expired and creds.refresh_token:
                creds.refresh(_Request())

            # Build service
            return build("gmail", "v1", credentials=creds, cache_discovery=False)

        except Exception as e:
            logger.exception("Failed to create Gmail service", error=str(e))
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

    def _build_query(self, config: dict[str, Any], since: datetime) -> str:
        """Build Gmail search query.

        Args:
            config: Collection config with optional query.
            since: Fetch emails after this date.

        Returns:
            Gmail query string.

        """
        # Format date for Gmail query (YYYY/MM/DD)
        since_str = since.strftime("%Y/%m/%d")

        # Use custom query if provided
        custom_query = config.get("query", "")

        if custom_query:
            # Append date filter if not already present
            if "after:" not in custom_query.lower():
                return f"({custom_query}) after:{since_str}"
            return str(custom_query)

        # Default query: newer emails
        return f"after:{since_str}"

    def _list_messages(
        self,
        service: Any,
        query: str,
        labels: list[str],
        max_results: int,
    ) -> list[dict[str, Any]]:
        """List messages matching query.

        Args:
            service: Gmail API service.
            query: Search query.
            labels: Label IDs to filter.
            max_results: Maximum results to return.

        Returns:
            List of message info dicts with id and threadId.

        """
        messages: list[dict[str, Any]] = []
        page_token = None

        while len(messages) < max_results:
            remaining = max_results - len(messages)
            result = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    labelIds=labels,
                    maxResults=min(remaining, 100),
                    pageToken=page_token,
                )
                .execute()
            )

            batch = result.get("messages", [])
            messages.extend(batch)

            page_token = result.get("nextPageToken")
            if not page_token or not batch:
                break

        return messages[:max_results]

    def _get_message(self, service: Any, message_id: str) -> dict[str, Any] | None:
        """Get full message details.

        Args:
            service: Gmail API service.
            message_id: Message ID.

        Returns:
            Full message data or None on error.

        """
        result: dict[str, Any] | None = None
        try:
            result = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        except HttpError as e:
            logger.warning("Failed to get message", message_id=message_id, error=str(e))

        return result

    def _message_to_digest_item(
        self,
        source_id: str,
        message: dict[str, Any],
    ) -> DigestItem:
        """Convert Gmail message to DigestItem.

        Args:
            source_id: ID of the source.
            message: Gmail message dictionary.

        Returns:
            DigestItem representing the email.

        """
        msg_id = message.get("id", "")
        thread_id = message.get("threadId", "")
        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        # Extract headers
        subject = self._get_header(headers, "Subject") or "(No Subject)"
        sender = self._get_header(headers, "From") or ""
        to = self._get_header(headers, "To") or ""
        date_str = self._get_header(headers, "Date")

        # Parse date
        received_at = self._parse_email_date(date_str)

        # Get snippet (preview text)
        snippet = message.get("snippet", "")

        # Get labels
        labels = message.get("labelIds", [])

        # Check if unread
        is_unread = "UNREAD" in labels

        # Extract body preview
        body_preview = self._extract_body_preview(payload)

        # Build content
        content = {
            "message_id": msg_id,
            "thread_id": thread_id,
            "subject": subject,
            "sender": sender,
            "to": to,
            "snippet": snippet,
            "body_preview": body_preview,
            "labels": labels,
            "is_unread": is_unread,
        }

        # Metadata for quick access
        metadata = {
            "sender": self._extract_sender_name(sender),
            "is_unread": is_unread,
            "labels": labels,
        }

        return self.create_digest_item(
            source_id=source_id,
            external_id=msg_id,
            item_type=ItemType.EMAIL,
            title=subject,
            content=content,
            metadata=metadata,
            external_url=f"https://mail.google.com/mail/u/0/#inbox/{msg_id}",
            external_created_at=received_at,
            external_updated_at=received_at,
        )

    @staticmethod
    def _get_header(headers: list[dict[str, str]], name: str) -> str | None:
        """Get header value by name.

        Args:
            headers: List of header dicts.
            name: Header name to find.

        Returns:
            Header value or None.

        """
        for header in headers:
            if header.get("name", "").lower() == name.lower():
                return header.get("value")
        return None

    @staticmethod
    def _parse_email_date(date_str: str | None) -> datetime | None:
        """Parse email date header to datetime.

        Args:
            date_str: Email date string (RFC 2822 format).

        Returns:
            Parsed datetime or None.

        """
        if not date_str:
            return None

        try:
            dt = parsedate_to_datetime(date_str)
            return dt.astimezone(UTC)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_sender_name(sender: str) -> str:
        """Extract sender name from From header.

        Args:
            sender: From header value (e.g., "John Doe <john@example.com>").

        Returns:
            Sender name or email.

        """
        if "<" in sender:
            return sender.split("<")[0].strip().strip('"')
        return sender

    def _extract_body_preview(self, payload: dict[str, Any], max_length: int = 200) -> str:
        """Extract body preview from message payload.

        Args:
            payload: Message payload.
            max_length: Maximum preview length.

        Returns:
            Body preview text.

        """
        # Try to get plain text body
        body_data = self._get_body_data(payload, "text/plain")

        # Fall back to HTML if no plain text
        if not body_data:
            body_data = self._get_body_data(payload, "text/html")

        if not body_data:
            return ""

        try:
            decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
            # Strip HTML tags if HTML content
            if "<" in decoded:
                decoded = re.sub(r"<[^>]+>", "", decoded)
            # Clean up whitespace
            decoded = " ".join(decoded.split())
            return decoded[:max_length]
        except Exception:
            return ""

    def _get_body_data(self, payload: dict[str, Any], mime_type: str) -> str | None:
        """Get body data for specific MIME type.

        Args:
            payload: Message payload.
            mime_type: MIME type to find.

        Returns:
            Base64 encoded body data or None.

        """
        # Check if payload itself matches
        if payload.get("mimeType") == mime_type:
            body = payload.get("body", {})
            data = body.get("data")
            return str(data) if data else None

        # Check parts
        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == mime_type:
                body = part.get("body", {})
                data = body.get("data")
                return str(data) if data else None

            # Recurse into nested parts
            nested = self._get_body_data(part, mime_type)
            if nested:
                return nested

        return None
