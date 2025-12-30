"""Slack collector implementation."""

from datetime import UTC, datetime
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

SLACK_API_BASE = "https://slack.com/api"


@CollectorRegistry.register(SourceType.SLACK)
class SlackCollector(BaseCollector):
    """Collector for Slack messages.

    Uses Slack Bot Token for authentication.

    Credentials format:
        {
            "bot_token": "xoxb-..."
        }

    Config format:
        {
            "channel_ids": ["C01234567"],  # Channel IDs to monitor
            "max_messages": 50,  # Max messages per channel
            "include_threads": true  # Include thread replies
        }
    """

    @property
    def source_type(self) -> SourceType:
        """Return the source type for this collector."""
        return SourceType.SLACK

    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect messages from Slack channels.

        Args:
            source_id: ID of the source.
            credentials: Slack bot token credentials.
            config: Collection config (channel_ids, max_messages, include_threads).
            since: Fetch messages after this time.

        Returns:
            List of DigestItems representing Slack messages.

        """
        log = logger.bind(source_id=source_id)
        log.info("Starting Slack collection")

        bot_token = credentials.get("bot_token", "")
        if not bot_token:
            err_msg = "Missing Slack bot token"
            raise AuthenticationError(err_msg)

        channel_ids = config.get("channel_ids", [])
        max_messages = config.get("max_messages", 50)
        include_threads = config.get("include_threads", True)

        since_dt = self.get_since_datetime(since)
        oldest_ts = str(since_dt.timestamp())

        log.debug(
            "Fetching messages",
            channel_ids=channel_ids,
            oldest=oldest_ts,
        )

        items: list[DigestItem] = []
        client = await self.get_client()

        try:
            # Get channel info for names
            channels_info = await self._get_channels_info(client, bot_token, channel_ids)

            for channel_id in channel_ids:
                channel_name = channels_info.get(channel_id, {}).get("name", channel_id)

                messages = await self._fetch_channel_messages(
                    client,
                    bot_token,
                    channel_id,
                    oldest_ts,
                    max_messages,
                )

                for msg in messages:
                    # Skip bot messages, join/leave messages, etc.
                    if msg.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
                        continue

                    item = self._message_to_digest_item(
                        source_id,
                        channel_id,
                        channel_name,
                        msg,
                    )
                    items.append(item)

                    # Fetch thread replies if configured
                    if include_threads and msg.get("reply_count", 0) > 0:
                        thread_ts = msg.get("ts", "")
                        replies = await self._fetch_thread_replies(
                            client,
                            bot_token,
                            channel_id,
                            thread_ts,
                            oldest_ts,
                        )
                        for reply in replies:
                            if reply.get("ts") != thread_ts:  # Skip parent
                                reply_item = self._message_to_digest_item(
                                    source_id,
                                    channel_id,
                                    channel_name,
                                    reply,
                                    is_thread_reply=True,
                                )
                                items.append(reply_item)

            log.info("Slack collection completed", message_count=len(items))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                err_msg = "Slack token invalid or expired"
                raise AuthenticationError(err_msg) from e
            err_msg = f"Slack API error: {e}"
            raise CollectorError(
                err_msg,
                error_type="slack_api",
                recoverable=e.response.status_code >= 500,
            ) from e

        return items

    async def validate_credentials(
        self,
        credentials: dict[str, Any],
    ) -> bool:
        """Validate Slack credentials by testing auth.

        Args:
            credentials: Slack bot token credentials to validate.

        Returns:
            True if credentials are valid.

        """
        bot_token = credentials.get("bot_token", "")
        if not bot_token:
            return False

        client = await self.get_client()

        try:
            response = await client.get(
                f"{SLACK_API_BASE}/auth.test",
                headers={"Authorization": f"Bearer {bot_token}"},
            )
            data = response.json()
            return bool(data.get("ok", False))
        except Exception:
            return False

    async def _get_channels_info(
        self,
        client: httpx.AsyncClient,
        bot_token: str,
        channel_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Get channel information.

        Args:
            client: HTTP client.
            bot_token: Slack bot token.
            channel_ids: List of channel IDs.

        Returns:
            Dict mapping channel ID to channel info.

        """
        channels_info: dict[str, dict[str, Any]] = {}

        for channel_id in channel_ids:
            try:
                response = await client.get(
                    f"{SLACK_API_BASE}/conversations.info",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    params={"channel": channel_id},
                )
                data = response.json()
                if data.get("ok"):
                    channels_info[channel_id] = data.get("channel", {})
            except Exception as e:
                logger.warning(
                    "Failed to get channel info",
                    channel_id=channel_id,
                    error=str(e),
                )

        return channels_info

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        bot_token: str,
        channel_id: str,
        oldest: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch messages from a channel.

        Args:
            client: HTTP client.
            bot_token: Slack bot token.
            channel_id: Channel ID.
            oldest: Oldest timestamp (Unix).
            limit: Maximum messages to fetch.

        Returns:
            List of message dictionaries.

        """
        messages: list[dict[str, Any]] = []
        cursor = None

        while len(messages) < limit:
            params: dict[str, Any] = {
                "channel": channel_id,
                "oldest": oldest,
                "limit": min(limit - len(messages), 100),
            }
            if cursor:
                params["cursor"] = cursor

            response = await client.get(
                f"{SLACK_API_BASE}/conversations.history",
                headers={"Authorization": f"Bearer {bot_token}"},
                params=params,
            )

            data = response.json()
            if not data.get("ok"):
                error = data.get("error", "unknown")
                logger.warning(
                    "Failed to fetch messages",
                    channel_id=channel_id,
                    error=error,
                )
                break

            batch = data.get("messages", [])
            messages.extend(batch)

            # Check for pagination
            response_metadata = data.get("response_metadata", {})
            cursor = response_metadata.get("next_cursor")
            if not cursor or not batch:
                break

        return messages[:limit]

    async def _fetch_thread_replies(
        self,
        client: httpx.AsyncClient,
        bot_token: str,
        channel_id: str,
        thread_ts: str,
        oldest: str,
    ) -> list[dict[str, Any]]:
        """Fetch replies in a thread.

        Args:
            client: HTTP client.
            bot_token: Slack bot token.
            channel_id: Channel ID.
            thread_ts: Thread timestamp.
            oldest: Oldest timestamp filter.

        Returns:
            List of reply message dictionaries.

        """
        try:
            response = await client.get(
                f"{SLACK_API_BASE}/conversations.replies",
                headers={"Authorization": f"Bearer {bot_token}"},
                params={
                    "channel": channel_id,
                    "ts": thread_ts,
                    "oldest": oldest,
                    "limit": 50,
                },
            )

            data = response.json()
            if data.get("ok"):
                messages: list[dict[str, Any]] = data.get("messages", [])
                return messages
        except Exception as e:
            logger.warning(
                "Failed to fetch thread replies",
                channel_id=channel_id,
                thread_ts=thread_ts,
                error=str(e),
            )

        return []

    def _message_to_digest_item(
        self,
        source_id: str,
        channel_id: str,
        channel_name: str,
        message: dict[str, Any],
        *,
        is_thread_reply: bool = False,
    ) -> DigestItem:
        """Convert Slack message to DigestItem.

        Args:
            source_id: ID of the source.
            channel_id: Channel ID.
            channel_name: Channel name.
            message: Slack message dictionary.
            is_thread_reply: Whether this is a thread reply.

        Returns:
            DigestItem representing the message.

        """
        ts = message.get("ts", "")
        user = message.get("user", "")
        text = message.get("text", "")
        thread_ts = message.get("thread_ts")
        reply_count = message.get("reply_count", 0)

        # Parse timestamp
        msg_datetime = self._parse_slack_ts(ts)

        # Truncate text for title (first line, max 100 chars)
        title_text = text.split("\n")[0][:100] if text else "(no message)"
        if len(title_text) < len(text.split("\n")[0]):
            title_text += "..."

        # Build message ID
        msg_id = f"{channel_id}:{ts}"

        # Build URL
        # Format: https://workspace.slack.com/archives/CHANNEL_ID/pTIMESTAMP
        # We don't have workspace URL, so use a placeholder format
        ts_for_url = ts.replace(".", "")
        external_url = f"slack://channel?team=T&id={channel_id}&message={ts_for_url}"

        # Build content
        content = {
            "message_ts": ts,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "user": user,
            "text": text,
            "is_thread_reply": is_thread_reply,
            "thread_ts": thread_ts,
            "reply_count": reply_count,
            "has_attachments": len(message.get("attachments", [])) > 0,
            "has_files": len(message.get("files", [])) > 0,
        }

        # Metadata
        metadata = {
            "channel": channel_name,
            "user": user,
            "is_thread_reply": is_thread_reply,
            "reply_count": reply_count,
        }

        return self.create_digest_item(
            source_id=source_id,
            external_id=msg_id,
            item_type=ItemType.MESSAGE,
            title=f"#{channel_name}: {title_text}",
            content=content,
            metadata=metadata,
            external_url=external_url,
            external_created_at=msg_datetime,
            external_updated_at=msg_datetime,
        )

    @staticmethod
    def _parse_slack_ts(ts: str | None) -> datetime | None:
        """Parse Slack timestamp to datetime.

        Args:
            ts: Slack timestamp (Unix epoch with microseconds), or None.

        Returns:
            Parsed datetime or None.

        """
        if not ts:
            return None

        try:
            # Slack ts format: "1234567890.123456"
            epoch = float(ts)
            return datetime.fromtimestamp(epoch, tz=UTC)
        except (ValueError, TypeError):
            return None
