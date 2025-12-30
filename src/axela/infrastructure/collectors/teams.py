"""Microsoft Teams collector implementation using Microsoft Graph API."""

import re
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


@CollectorRegistry.register(SourceType.TEAMS)
class TeamsCollector(BaseCollector):
    """Collector for Microsoft Teams messages.

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
            "team_ids": ["..."],  # Team IDs to monitor
            "channel_ids": ["..."],  # Optional: specific channel IDs
            "max_messages": 50,
            "include_replies": true
        }
    """

    @property
    def source_type(self) -> SourceType:
        """Return the source type for this collector."""
        return SourceType.TEAMS

    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect messages from Microsoft Teams.

        Args:
            source_id: ID of the source.
            credentials: Microsoft Graph OAuth2 credentials.
            config: Collection config (team_ids, channel_ids, max_messages).
            since: Fetch messages after this time.

        Returns:
            List of DigestItems representing Teams messages.

        """
        log = logger.bind(source_id=source_id)
        log.info("Starting Teams collection")

        access_token = credentials.get("access_token", "")
        if not access_token:
            err_msg = "Missing Teams access token"
            raise AuthenticationError(err_msg)

        team_ids = config.get("team_ids", [])
        channel_ids = config.get("channel_ids", [])
        max_messages = config.get("max_messages", 50)
        include_replies = config.get("include_replies", True)

        since_dt = self.get_since_datetime(since)

        log.debug(
            "Fetching messages",
            team_ids=team_ids,
            since=since_dt.isoformat(),
        )

        items: list[DigestItem] = []
        client = await self.get_client()

        try:
            # Get channels to monitor
            channels = await self._get_channels(client, access_token, team_ids, channel_ids)

            for channel_info in channels:
                team_id = channel_info["team_id"]
                channel_id = channel_info["channel_id"]
                channel_name = channel_info["channel_name"]
                team_name = channel_info["team_name"]

                messages = await self._fetch_channel_messages(
                    client,
                    access_token,
                    team_id,
                    channel_id,
                    since_dt,
                    max_messages,
                )

                for msg in messages:
                    item = self._message_to_digest_item(
                        source_id,
                        team_id,
                        team_name,
                        channel_id,
                        channel_name,
                        msg,
                    )
                    items.append(item)

                    # Fetch replies if configured
                    if include_replies and msg.get("replies"):
                        replies = await self._fetch_message_replies(
                            client,
                            access_token,
                            team_id,
                            channel_id,
                            msg["id"],
                            since_dt,
                        )
                        for reply in replies:
                            reply_item = self._message_to_digest_item(
                                source_id,
                                team_id,
                                team_name,
                                channel_id,
                                channel_name,
                                reply,
                                is_reply=True,
                            )
                            items.append(reply_item)

            log.info("Teams collection completed", message_count=len(items))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                err_msg = "Teams token invalid or expired"
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
        """Validate Teams credentials by fetching user profile.

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
            logger.debug("Teams credential validation failed", error=str(e))

        return valid

    async def _get_channels(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        team_ids: list[str],
        channel_ids: list[str],
    ) -> list[dict[str, str]]:
        """Get list of channels to monitor.

        Args:
            client: HTTP client.
            access_token: Microsoft Graph access token.
            team_ids: Team IDs to fetch channels from.
            channel_ids: Specific channel IDs to include.

        Returns:
            List of channel info dicts with team_id, channel_id, etc.

        """
        channels: list[dict[str, str]] = []

        for team_id in team_ids:
            try:
                # Get team info
                team_response = await client.get(
                    f"{GRAPH_API_BASE}/teams/{team_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                team_name = ""
                if team_response.is_success:
                    team_data = team_response.json()
                    team_name = team_data.get("displayName", "")

                # Get channels
                response = await client.get(
                    f"{GRAPH_API_BASE}/teams/{team_id}/channels",
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                if response.is_success:
                    data = response.json()
                    for ch in data.get("value", []):
                        ch_id = ch.get("id", "")
                        # Filter by channel_ids if specified
                        if channel_ids and ch_id not in channel_ids:
                            continue

                        channels.append(
                            {
                                "team_id": team_id,
                                "team_name": team_name,
                                "channel_id": ch_id,
                                "channel_name": ch.get("displayName", ""),
                            }
                        )
            except Exception as e:
                logger.warning(
                    "Failed to get channels for team",
                    team_id=team_id,
                    error=str(e),
                )

        return channels

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        team_id: str,
        channel_id: str,
        since: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch messages from a channel.

        Args:
            client: HTTP client.
            access_token: Microsoft Graph access token.
            team_id: Team ID.
            channel_id: Channel ID.
            since: Fetch messages after this time.
            limit: Maximum messages to fetch.

        Returns:
            List of message dictionaries.

        """
        messages: list[dict[str, Any]] = []

        url = f"{GRAPH_API_BASE}/teams/{team_id}/channels/{channel_id}/messages"
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        params: dict[str, str | int] = {
            "$filter": f"createdDateTime ge {since_str}",
            "$top": min(limit, 50),
            "$orderby": "createdDateTime desc",
        }

        next_link: str | None = url

        while next_link and len(messages) < limit:
            try:
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
                        team_id=team_id,
                        channel_id=channel_id,
                        status=response.status_code,
                    )
                    break

                data = response.json()
                batch = data.get("value", [])
                messages.extend(batch)

                next_link = data.get("@odata.nextLink")
                if not batch:
                    break
            except Exception as e:
                logger.warning(
                    "Error fetching messages",
                    team_id=team_id,
                    channel_id=channel_id,
                    error=str(e),
                )
                break

        return messages[:limit]

    async def _fetch_message_replies(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        team_id: str,
        channel_id: str,
        message_id: str,
        since: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch replies to a message.

        Args:
            client: HTTP client.
            access_token: Microsoft Graph access token.
            team_id: Team ID.
            channel_id: Channel ID.
            message_id: Parent message ID.
            since: Fetch replies after this time.

        Returns:
            List of reply dictionaries.

        """
        url = f"{GRAPH_API_BASE}/teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies"
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "$filter": f"createdDateTime ge {since_str}",
                    "$top": 20,
                },
            )

            if response.is_success:
                data = response.json()
                replies: list[dict[str, Any]] = data.get("value", [])
                return replies
        except Exception as e:
            logger.warning(
                "Failed to fetch replies",
                message_id=message_id,
                error=str(e),
            )

        return []

    def _message_to_digest_item(
        self,
        source_id: str,
        team_id: str,
        team_name: str,
        channel_id: str,
        channel_name: str,
        message: dict[str, Any],
        *,
        is_reply: bool = False,
    ) -> DigestItem:
        """Convert Teams message to DigestItem.

        Args:
            source_id: ID of the source.
            team_id: Team ID.
            team_name: Team display name.
            channel_id: Channel ID.
            channel_name: Channel display name.
            message: Microsoft Graph message dictionary.
            is_reply: Whether this is a reply message.

        Returns:
            DigestItem representing the message.

        """
        msg_id = message.get("id", "")
        body = message.get("body", {})
        content_text = body.get("content", "")
        content_type = body.get("contentType", "text")

        # Strip HTML if HTML content
        if content_type == "html" and "<" in content_text:
            content_text = re.sub(r"<[^>]+>", "", content_text)

        # Parse sender
        from_info = message.get("from", {})
        user_info = from_info.get("user", {})
        sender_name = user_info.get("displayName", "")
        sender_id = user_info.get("id", "")

        # Parse dates
        created_str = message.get("createdDateTime", "")
        created_at = self._parse_graph_datetime(created_str)

        modified_str = message.get("lastModifiedDateTime", "")
        modified_at = self._parse_graph_datetime(modified_str)

        # Message importance
        importance = message.get("importance", "normal")

        # Has attachments
        attachments = message.get("attachments", [])
        has_attachments = len(attachments) > 0

        # Has mentions
        mentions = message.get("mentions", [])
        mention_names = [m.get("mentioned", {}).get("user", {}).get("displayName", "") for m in mentions]

        # Build title - truncate content
        title_text = content_text[:100].split("\n")[0]
        if len(title_text) < len(content_text.split("\n")[0]):
            title_text += "..."

        # Build content
        content = {
            "message_id": msg_id,
            "team_id": team_id,
            "team_name": team_name,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "sender_name": sender_name,
            "sender_id": sender_id,
            "body": content_text,
            "content_type": content_type,
            "is_reply": is_reply,
            "importance": importance,
            "has_attachments": has_attachments,
            "mentions": mention_names,
        }

        # Metadata
        metadata = {
            "team": team_name,
            "channel": channel_name,
            "sender": sender_name,
            "is_reply": is_reply,
            "importance": importance,
        }

        # Build external URL (deep link to Teams)
        external_url = (
            f"https://teams.microsoft.com/l/message/{channel_id}/{msg_id}"
            f"?tenantId=&groupId={team_id}&parentMessageId={msg_id}"
        )

        return self.create_digest_item(
            source_id=source_id,
            external_id=msg_id,
            item_type=ItemType.MESSAGE,
            title=f"[{team_name}] #{channel_name}: {title_text}",
            content=content,
            metadata=metadata,
            external_url=external_url,
            external_created_at=created_at,
            external_updated_at=modified_at,
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
            return datetime.fromisoformat(dt_str)
        except ValueError:
            return None
