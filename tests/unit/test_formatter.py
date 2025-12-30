"""Tests for Telegram message formatter."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from axela.domain.enums import DigestType, ItemType
from axela.domain.models import DigestItem, Project
from axela.infrastructure.telegram.formatter import (
    format_digest,
    format_error_alert,
    format_status,
)


class TestFormatDigest:
    """Tests for format_digest function."""

    @pytest.fixture
    def sample_project(self) -> Project:
        """Sample project."""
        return Project(
            id=uuid4(),
            name="Test Project",
            color="#FF0000",
            created_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_item(self) -> DigestItem:
        """Sample digest item."""
        return DigestItem(
            source_id=uuid4(),
            external_id="item-123",
            item_type=ItemType.ISSUE,
            title="Fix critical bug",
            content={
                "status": "In Progress",
                "priority": "High",
                "assignee": "John Doe",
            },
            content_hash="abc123",
            metadata={"key": "value"},
            external_url="https://example.com/issue/123",
            external_created_at=datetime.now(UTC),
            external_updated_at=datetime.now(UTC),
        )

    def test_format_empty_digest_russian(self) -> None:
        """Test formatting empty digest in Russian."""
        result = format_digest([], DigestType.MORNING, "ru")
        assert "Нет новых обновлений" in result

    def test_format_empty_digest_english(self) -> None:
        """Test formatting empty digest in English."""
        result = format_digest([], DigestType.MORNING, "en")
        assert "No new updates" in result

    def test_format_morning_digest_header_russian(
        self,
        sample_item: DigestItem,
        sample_project: Project,
    ) -> None:
        """Test morning digest header in Russian."""
        items = [(sample_item, uuid4(), sample_project)]
        result = format_digest(items, DigestType.MORNING, "ru")
        assert "Утренний дайджест" in result

    def test_format_evening_digest_header_russian(
        self,
        sample_item: DigestItem,
        sample_project: Project,
    ) -> None:
        """Test evening digest header in Russian."""
        items = [(sample_item, uuid4(), sample_project)]
        result = format_digest(items, DigestType.EVENING, "ru")
        assert "Вечерний дайджест" in result

    def test_format_morning_digest_header_english(
        self,
        sample_item: DigestItem,
        sample_project: Project,
    ) -> None:
        """Test morning digest header in English."""
        items = [(sample_item, uuid4(), sample_project)]
        result = format_digest(items, DigestType.MORNING, "en")
        assert "Morning Digest" in result

    def test_format_digest_includes_project_name(
        self,
        sample_item: DigestItem,
        sample_project: Project,
    ) -> None:
        """Test that digest includes project name."""
        items = [(sample_item, uuid4(), sample_project)]
        result = format_digest(items, DigestType.ON_DEMAND, "en")
        assert sample_project.name in result

    def test_format_digest_includes_item_title(
        self,
        sample_item: DigestItem,
        sample_project: Project,
    ) -> None:
        """Test that digest includes item title."""
        items = [(sample_item, uuid4(), sample_project)]
        result = format_digest(items, DigestType.ON_DEMAND, "en")
        assert sample_item.title is not None
        assert sample_item.title in result

    def test_format_digest_includes_item_url(
        self,
        sample_item: DigestItem,
        sample_project: Project,
    ) -> None:
        """Test that digest includes item URL as link."""
        items = [(sample_item, uuid4(), sample_project)]
        result = format_digest(items, DigestType.ON_DEMAND, "en")
        assert sample_item.external_url is not None
        assert sample_item.external_url in result
        assert f'href="{sample_item.external_url}"' in result

    def test_format_digest_multiple_projects(self) -> None:
        """Test formatting digest with multiple projects."""
        project1 = Project(id=uuid4(), name="Project A", color="#FF0000")
        project2 = Project(id=uuid4(), name="Project B", color="#00FF00")

        item1 = DigestItem(
            source_id=uuid4(),
            external_id="item-1",
            item_type=ItemType.ISSUE,
            title="Item in Project A",
            content={},
            content_hash="hash1",
        )
        item2 = DigestItem(
            source_id=uuid4(),
            external_id="item-2",
            item_type=ItemType.EMAIL,
            title="Item in Project B",
            content={},
            content_hash="hash2",
        )

        items = [
            (item1, uuid4(), project1),
            (item2, uuid4(), project2),
        ]
        result = format_digest(items, DigestType.ON_DEMAND, "en")

        assert "Project A" in result
        assert "Project B" in result
        assert "Item in Project A" in result
        assert "Item in Project B" in result

    def test_format_digest_item_count(
        self,
        sample_item: DigestItem,
        sample_project: Project,
    ) -> None:
        """Test that digest shows correct item count."""
        items = [(sample_item, uuid4(), sample_project)]
        result = format_digest(items, DigestType.ON_DEMAND, "en")
        assert "1 update" in result

    def test_format_digest_multiple_items_count(
        self,
        sample_project: Project,
    ) -> None:
        """Test that digest shows correct count for multiple items."""
        items = []
        for i in range(3):
            item = DigestItem(
                source_id=uuid4(),
                external_id=f"item-{i}",
                item_type=ItemType.ISSUE,
                title=f"Item {i}",
                content={},
                content_hash=f"hash{i}",
            )
            items.append((item, uuid4(), sample_project))

        result = format_digest(items, DigestType.ON_DEMAND, "en")
        assert "3 updates" in result


class TestFormatErrorAlert:
    """Tests for format_error_alert function."""

    def test_format_error_russian(self) -> None:
        """Test error alert formatting in Russian."""
        result = format_error_alert(
            source_name="Gmail",
            error_type="auth",
            error_message="Token expired",
            language="ru",
        )

        assert "Ошибка коллектора" in result
        assert "Источник" in result
        assert "Gmail" in result
        assert "auth" in result
        assert "Token expired" in result

    def test_format_error_english(self) -> None:
        """Test error alert formatting in English."""
        result = format_error_alert(
            source_name="Jira",
            error_type="network",
            error_message="Connection timeout",
            language="en",
        )

        assert "Collector Error" in result
        assert "Source" in result
        assert "Jira" in result
        assert "network" in result
        assert "Connection timeout" in result

    def test_format_error_escapes_html(self) -> None:
        """Test that HTML special characters are escaped."""
        result = format_error_alert(
            source_name="Test <script>",
            error_type="test",
            error_message="<b>Error</b>",
            language="en",
        )

        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "&lt;b&gt;" in result


class TestFormatStatus:
    """Tests for format_status function."""

    def test_format_status_russian(self) -> None:
        """Test status formatting in Russian."""
        result = format_status(
            sources_count=5,
            schedules_count=3,
            last_digest_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            language="ru",
        )

        assert "Статус Axela" in result
        assert "Бот работает" in result
        assert "Источников: 5" in result
        assert "Расписаний: 3" in result
        assert "15.01.2024 10:30" in result

    def test_format_status_english(self) -> None:
        """Test status formatting in English."""
        result = format_status(
            sources_count=2,
            schedules_count=1,
            last_digest_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            language="en",
        )

        assert "Axela Status" in result
        assert "Bot is running" in result
        assert "Sources: 2" in result
        assert "Schedules: 1" in result
        assert "2024-01-15 10:30" in result

    def test_format_status_no_digest_russian(self) -> None:
        """Test status when no digest sent yet in Russian."""
        result = format_status(
            sources_count=0,
            schedules_count=0,
            last_digest_at=None,
            language="ru",
        )

        assert "Дайджесты ещё не отправлялись" in result

    def test_format_status_no_digest_english(self) -> None:
        """Test status when no digest sent yet in English."""
        result = format_status(
            sources_count=0,
            schedules_count=0,
            last_digest_at=None,
            language="en",
        )

        assert "No digests sent yet" in result
