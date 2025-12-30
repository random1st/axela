"""Jira collector implementation."""

from datetime import UTC, datetime
from typing import Any

import structlog

from axela.application.ports.collector import AuthenticationError, ConfigurationError
from axela.domain.enums import ItemType, SourceType
from axela.domain.models import DigestItem

from .base import BaseCollector, CollectorRegistry

logger = structlog.get_logger()


@CollectorRegistry.register(SourceType.JIRA)
class JiraCollector(BaseCollector):
    """Collector for Jira issues.

    Uses Jira REST API v3 with Basic Auth (email + API token).

    Credentials format:
        {
            "url": "https://your-domain.atlassian.net",
            "email": "user@example.com",
            "api_token": "your-api-token"
        }

    Config format:
        {
            "jql": "assignee = currentUser() AND updated >= -7d",
            "max_results": 50
        }
    """

    @property
    def source_type(self) -> SourceType:
        """Return the source type for this collector."""
        return SourceType.JIRA

    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect issues from Jira.

        Args:
            source_id: ID of the source.
            credentials: Jira credentials (url, email, api_token).
            config: Collection config (jql, max_results).
            since: Fetch issues updated since this time.

        Returns:
            List of DigestItems representing Jira issues.

        """
        log = logger.bind(source_id=source_id)
        log.info("Starting Jira collection")

        # Validate credentials
        url = credentials.get("url", "").rstrip("/")
        email = credentials.get("email", "")
        api_token = credentials.get("api_token", "")

        if not all([url, email, api_token]):
            msg = "Missing required credentials: url, email, api_token"
            raise ConfigurationError(msg)

        # Type assertions after validation
        assert isinstance(email, str)
        assert isinstance(api_token, str)

        # Build JQL query
        since_dt = self.get_since_datetime(since)
        jql = self._build_jql(config, since_dt)
        max_results = config.get("max_results", 50)

        log.debug("Fetching issues", jql=jql, max_results=max_results)

        # Fetch issues from Jira API
        client = await self.get_client()
        issues = await self._fetch_issues(
            client=client,
            url=url,
            email=email,
            api_token=api_token,
            jql=jql,
            max_results=max_results,
        )

        # Convert to DigestItems
        items = []
        for issue in issues:
            item = self._issue_to_digest_item(source_id, url, issue)
            items.append(item)

        log.info("Jira collection completed", issue_count=len(items))
        return items

    async def validate_credentials(
        self,
        credentials: dict[str, Any],
    ) -> bool:
        """Validate Jira credentials by fetching current user.

        Args:
            credentials: Jira credentials to validate.

        Returns:
            True if credentials are valid.

        """
        url = credentials.get("url", "").rstrip("/")
        email = credentials.get("email", "")
        api_token = credentials.get("api_token", "")

        if not all([url, email, api_token]):
            return False

        if not isinstance(email, str) or not isinstance(api_token, str):
            return False

        client = await self.get_client()
        valid = False
        try:
            response = await client.get(
                f"{url}/rest/api/3/myself",
                auth=(email, api_token),
            )
            valid = response.is_success
        except Exception as e:
            logger.debug("Jira credential validation failed", error=str(e))

        return valid

    def _build_jql(
        self,
        config: dict[str, Any],
        since: datetime,
    ) -> str:
        """Build JQL query for fetching issues.

        Args:
            config: Collection config with optional custom JQL.
            since: Fetch issues updated since this time.

        Returns:
            JQL query string.

        """
        # Use custom JQL if provided
        custom_jql = config.get("jql")
        if custom_jql and isinstance(custom_jql, str):
            # Append date filter if not already present
            if "updated" not in custom_jql.lower():
                since_str = since.strftime("%Y-%m-%d %H:%M")
                return f"({custom_jql}) AND updated >= '{since_str}'"
            return str(custom_jql)

        # Default JQL: assigned issues updated since
        since_str = since.strftime("%Y-%m-%d %H:%M")
        return f"assignee = currentUser() AND updated >= '{since_str}' ORDER BY updated DESC"

    async def _fetch_issues(
        self,
        client: Any,
        url: str,
        email: str,
        api_token: str,
        jql: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Fetch issues from Jira API.

        Args:
            client: HTTP client.
            url: Jira base URL.
            email: User email.
            api_token: API token.
            jql: JQL query.
            max_results: Maximum number of results.

        Returns:
            List of issue dictionaries.

        """
        request_fields = "summary,status,priority,assignee,reporter,created,updated,description,issuetype,project"
        response = await client.get(
            f"{url}/rest/api/3/search",
            params={"jql": jql, "maxResults": max_results, "fields": request_fields},
            auth=(email, api_token),
        )

        if response.status_code == 401:
            msg = "Invalid Jira credentials"
            raise AuthenticationError(msg)

        await self.handle_response_error(response, "Jira API")

        data = response.json()
        issues = data.get("issues", [])
        return list(issues) if isinstance(issues, list) else []

    def _issue_to_digest_item(
        self,
        source_id: str,
        base_url: str,
        issue: dict[str, Any],
    ) -> DigestItem:
        """Convert Jira issue to DigestItem.

        Args:
            source_id: ID of the source.
            base_url: Jira base URL.
            issue: Jira issue dictionary.

        Returns:
            DigestItem representing the issue.

        """
        fields = issue.get("fields", {})
        key = issue.get("key", "")

        # Extract fields
        summary = fields.get("summary", "")
        status = fields.get("status", {}).get("name", "")
        priority = fields.get("priority", {}).get("name") if fields.get("priority") else None
        issue_type = fields.get("issuetype", {}).get("name", "")
        project_name = fields.get("project", {}).get("name", "")

        # Assignee
        assignee_data = fields.get("assignee")
        assignee = assignee_data.get("displayName") if assignee_data else None

        # Reporter
        reporter_data = fields.get("reporter")
        reporter = reporter_data.get("displayName") if reporter_data else None

        # Timestamps
        created_at = self._parse_jira_date(fields.get("created"))
        updated_at = self._parse_jira_date(fields.get("updated"))

        # Build content for hashing and storage
        content = {
            "key": key,
            "summary": summary,
            "status": status,
            "priority": priority,
            "issue_type": issue_type,
            "project": project_name,
            "assignee": assignee,
            "reporter": reporter,
            "description": fields.get("description"),
        }

        # Metadata for quick access
        metadata = {
            "key": key,
            "status": status,
            "priority": priority,
            "issue_type": issue_type,
            "project": project_name,
        }

        return self.create_digest_item(
            source_id=source_id,
            external_id=key,
            item_type=ItemType.ISSUE,
            title=f"[{key}] {summary}",
            content=content,
            metadata=metadata,
            external_url=f"{base_url}/browse/{key}",
            external_created_at=created_at,
            external_updated_at=updated_at,
        )

    @staticmethod
    def _parse_jira_date(date_str: str | None) -> datetime | None:
        """Parse Jira date string to datetime.

        Args:
            date_str: Jira date string (ISO 8601 format).

        Returns:
            Parsed datetime or None.

        """
        if not date_str:
            return None

        try:
            # Jira uses ISO 8601 format: 2024-01-15T10:30:00.000+0000
            # Python's fromisoformat handles most cases
            # Remove milliseconds and normalize timezone
            if "." in date_str:
                date_str = date_str.split(".")[0]
            if "+" in date_str:
                date_str = date_str.split("+")[0]
            if "Z" in date_str:
                date_str = date_str.replace("Z", "")

            dt = datetime.fromisoformat(date_str)
            return dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None
