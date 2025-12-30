"""Tests for Jira collector."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from axela.domain.enums import ItemType, SourceType
from axela.infrastructure.collectors.jira import JiraCollector


class TestJiraCollector:
    """Tests for JiraCollector."""

    @pytest.fixture
    def collector(self) -> JiraCollector:
        """Create a JiraCollector instance."""
        return JiraCollector()

    @pytest.fixture
    def valid_credentials(self) -> dict[str, Any]:
        """Return valid Jira credentials."""
        return {
            "url": "https://test.atlassian.net",
            "email": "test@example.com",
            "api_token": "test-token",
        }

    @pytest.fixture
    def sample_jira_response(self) -> dict[str, Any]:
        """Sample Jira API response."""
        return {
            "issues": [
                {
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "status": {"name": "In Progress"},
                        "priority": {"name": "High"},
                        "issuetype": {"name": "Bug"},
                        "project": {"name": "Test Project"},
                        "assignee": {"displayName": "John Doe"},
                        "reporter": {"displayName": "Jane Doe"},
                        "created": "2024-01-15T10:30:00.000+0000",
                        "updated": "2024-01-16T14:00:00.000+0000",
                        "description": "Test description",
                    },
                }
            ]
        }

    def test_source_type(self, collector: JiraCollector) -> None:
        """Test source_type property."""
        assert collector.source_type == SourceType.JIRA

    def test_build_jql_default(self, collector: JiraCollector) -> None:
        """Test default JQL generation."""
        since = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        jql = collector._build_jql({}, since)

        assert "assignee = currentUser()" in jql
        assert "updated >=" in jql
        assert "2024-01-15 10:00" in jql

    def test_build_jql_custom(self, collector: JiraCollector) -> None:
        """Test custom JQL with date filter appended."""
        since = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        config = {"jql": "project = TEST"}
        jql = collector._build_jql(config, since)

        assert "project = TEST" in jql
        assert "updated >=" in jql

    def test_build_jql_custom_with_updated(self, collector: JiraCollector) -> None:
        """Test custom JQL that already has updated filter."""
        since = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        config = {"jql": "project = TEST AND updated >= -1d"}
        jql = collector._build_jql(config, since)

        # Should not add another updated filter
        assert jql == "project = TEST AND updated >= -1d"

    def test_parse_jira_date(self, collector: JiraCollector) -> None:
        """Test Jira date parsing."""
        date_str = "2024-01-15T10:30:00.000+0000"
        result = collector._parse_jira_date(date_str)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_jira_date_none(self, collector: JiraCollector) -> None:
        """Test Jira date parsing with None."""
        assert collector._parse_jira_date(None) is None

    def test_parse_jira_date_invalid(self, collector: JiraCollector) -> None:
        """Test Jira date parsing with invalid string."""
        assert collector._parse_jira_date("invalid") is None

    @pytest.mark.asyncio
    async def test_collect_success(
        self,
        collector: JiraCollector,
        valid_credentials: dict[str, Any],
        sample_jira_response: dict[str, Any],
    ) -> None:
        """Test successful collection."""
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.status_code = 200
        mock_response.json.return_value = sample_jira_response

        with patch.object(collector, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            items = await collector.collect(
                source_id=str(uuid4()),
                credentials=valid_credentials,
                config={},
                since=datetime(2024, 1, 15, tzinfo=UTC),
            )

        assert len(items) == 1
        item = items[0]
        assert item.external_id == "TEST-123"
        assert item.item_type == ItemType.ISSUE
        assert item.title is not None
        assert "[TEST-123] Test issue" in item.title
        assert item.content["status"] == "In Progress"
        assert item.content["priority"] == "High"

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self,
        collector: JiraCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation success."""
        mock_response = MagicMock()
        mock_response.is_success = True

        with patch.object(collector, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await collector.validate_credentials(valid_credentials)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_credentials_failure(
        self,
        collector: JiraCollector,
        valid_credentials: dict[str, Any],
    ) -> None:
        """Test credential validation failure."""
        mock_response = MagicMock()
        mock_response.is_success = False

        with patch.object(collector, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await collector.validate_credentials(valid_credentials)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_credentials_missing(
        self,
        collector: JiraCollector,
    ) -> None:
        """Test credential validation with missing credentials."""
        result = await collector.validate_credentials({})
        assert result is False

    @pytest.mark.asyncio
    async def test_close(self, collector: JiraCollector) -> None:
        """Test collector close."""
        # Should not raise even without client
        await collector.close()
