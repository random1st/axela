"""Digest formatter for Telegram messages."""

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from axela.domain.enums import DigestType, ItemType
from axela.domain.models import DigestItem, Project


def format_digest(
    items: list[tuple[DigestItem, UUID, Project]],
    digest_type: DigestType,
    language: str = "ru",
) -> str:
    """Format digest items into a Telegram HTML message.

    Args:
        items: List of (item, item_id, project) tuples
        digest_type: Type of digest (morning, evening, etc.)
        language: Message language (ru or en)

    Returns:
        Formatted HTML string for Telegram

    """
    if not items:
        return _get_empty_message(digest_type, language)

    # Group items by project
    by_project: dict[UUID, list[tuple[DigestItem, UUID]]] = defaultdict(list)
    projects: dict[UUID, Project] = {}

    for item, item_id, project in items:
        by_project[project.id].append((item, item_id))
        projects[project.id] = project

    # Build message
    lines: list[str] = []

    # Header
    lines.append(_get_header(digest_type, len(items), language))
    lines.append("")

    # Items grouped by project
    for project_id, project_items in by_project.items():
        project = projects[project_id]
        color_emoji = _get_color_emoji(project.color)

        lines.append(f"{color_emoji} <b>{_escape_html(project.name)}</b>")
        lines.append("")

        for item, _ in project_items:
            formatted = _format_item(item)
            lines.append(formatted)

        lines.append("")

    # Footer
    lines.append(_get_footer(language))

    return "\n".join(lines)


def _get_header(digest_type: DigestType, count: int, language: str) -> str:
    """Get digest header based on type and language."""
    type_names = {
        "ru": {
            DigestType.MORNING: "🌅 Утренний дайджест",
            DigestType.EVENING: "🌆 Вечерний дайджест",
            DigestType.WEEKLY: "📅 Недельный дайджест",
            DigestType.MONTHLY: "📆 Месячный дайджест",
            DigestType.ON_DEMAND: "📋 Дайджест",
        },
        "en": {
            DigestType.MORNING: "🌅 Morning Digest",
            DigestType.EVENING: "🌆 Evening Digest",
            DigestType.WEEKLY: "📅 Weekly Digest",
            DigestType.MONTHLY: "📆 Monthly Digest",
            DigestType.ON_DEMAND: "📋 Digest",
        },
    }

    count_text = {
        "ru": f"{count} обновлений" if count != 1 else "1 обновление",
        "en": f"{count} updates" if count != 1 else "1 update",
    }

    lang = language if language in type_names else "en"
    title = type_names[lang].get(digest_type, type_names[lang][DigestType.ON_DEMAND])

    return f"<b>{title}</b> ({count_text[lang]})"


def _get_empty_message(digest_type: DigestType, language: str) -> str:  # noqa: ARG001
    """Get message for empty digest."""
    messages = {
        "ru": "✨ Нет новых обновлений",
        "en": "✨ No new updates",
    }
    lang = language if language in messages else "en"
    return messages[lang]


def _get_footer(language: str) -> str:
    """Get digest footer."""
    now = datetime.now(UTC)
    time_str = now.strftime("%H:%M")

    footers = {
        "ru": f"<i>Сгенерировано в {time_str}</i>",
        "en": f"<i>Generated at {time_str}</i>",
    }
    lang = language if language in footers else "en"
    return footers[lang]


def _format_item(item: DigestItem) -> str:
    """Format a single item for display."""
    icon = _get_item_icon(item.item_type)
    title = _escape_html(item.title or "Untitled")

    # Build item line
    line = f'{icon} <a href="{item.external_url}">{title}</a>' if item.external_url else f"{icon} {title}"

    # Add metadata based on item type
    meta_parts = _get_item_metadata(item)
    if meta_parts:
        meta_str = " · ".join(meta_parts)
        line += f"\n   <i>{meta_str}</i>"

    return line


def _get_item_icon(item_type: ItemType) -> str:
    """Get emoji icon for item type."""
    icons = {
        ItemType.ISSUE: "🎫",
        ItemType.EMAIL: "📧",
        ItemType.EVENT: "📅",
        ItemType.MESSAGE: "💬",
        ItemType.COMMENT: "💭",
        ItemType.THREAD_REPLY: "↩️",
        ItemType.MENTION: "📢",
    }
    return icons.get(item_type, "📌")


def _get_item_metadata(item: DigestItem) -> list[str]:
    """Extract relevant metadata from item content."""
    meta: list[str] = []
    content = item.content

    # Common metadata fields
    if status := content.get("status"):
        meta.append(_escape_html(str(status)))

    if priority := content.get("priority"):
        meta.append(_escape_html(str(priority)))

    if assignee := content.get("assignee"):
        meta.append(_escape_html(str(assignee)))

    if sender := content.get("sender"):
        meta.append(f"from {_escape_html(str(sender))}")

    if participants := content.get("participants"):
        if isinstance(participants, int):
            meta.append(f"{participants} participants")
        elif isinstance(participants, list) and len(participants) <= 3:
            meta.append(", ".join(_escape_html(str(p)) for p in participants))

    return meta


def _get_color_emoji(color: str | None) -> str:
    """Get emoji based on project color."""
    if not color:
        return "📁"

    # Map hex colors to closest emoji
    color_map = {
        "#FF0000": "🔴",
        "#00FF00": "🟢",
        "#0000FF": "🔵",
        "#FFFF00": "🟡",
        "#FF00FF": "🟣",
        "#00FFFF": "🔵",
        "#FFA500": "🟠",
        "#800080": "🟣",
        "#008000": "🟢",
        "#000000": "⚫",
        "#FFFFFF": "⚪",
    }

    # Normalize color
    color_upper = color.upper()
    if color_upper in color_map:
        return color_map[color_upper]

    # Return default based on first character of hex
    first_char = color_upper[1] if len(color_upper) > 1 else "0"
    defaults = {
        "F": "🟠",
        "E": "🟡",
        "D": "🟡",
        "C": "🟢",
        "B": "🔵",
        "A": "🔵",
        "9": "🟣",
        "8": "🟣",
    }
    return defaults.get(first_char, "📁")


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_error_alert(
    source_name: str,
    error_type: str,
    error_message: str,
    language: str = "ru",
) -> str:
    """Format collector error for Telegram alert.

    Args:
        source_name: Name of the source that failed
        error_type: Type of error
        error_message: Error description
        language: Message language

    Returns:
        Formatted HTML string

    """
    headers = {
        "ru": "⚠️ <b>Ошибка коллектора</b>",
        "en": "⚠️ <b>Collector Error</b>",
    }

    source_labels = {"ru": "Источник", "en": "Source"}
    type_labels = {"ru": "Тип", "en": "Type"}
    message_labels = {"ru": "Сообщение", "en": "Message"}

    lang = language if language in headers else "en"

    return (
        f"{headers[lang]}\n\n"
        f"<b>{source_labels[lang]}:</b> {_escape_html(source_name)}\n"
        f"<b>{type_labels[lang]}:</b> {_escape_html(error_type)}\n"
        f"<b>{message_labels[lang]}:</b> {_escape_html(error_message)}"
    )


def format_status(
    sources_count: int,
    schedules_count: int,
    last_digest_at: datetime | None,
    language: str = "ru",
) -> str:
    """Format bot status message.

    Args:
        sources_count: Number of active sources
        schedules_count: Number of active schedules
        last_digest_at: Time of last digest
        language: Message language

    Returns:
        Formatted HTML string

    """
    if language == "ru":
        lines = [
            "📊 <b>Статус Axela</b>",
            "",
            "✅ Бот работает",
            f"📥 Источников: {sources_count}",
            f"⏰ Расписаний: {schedules_count}",
        ]
        if last_digest_at:
            lines.append(f"📤 Последний дайджест: {last_digest_at.strftime('%d.%m.%Y %H:%M')}")
        else:
            lines.append("📤 Дайджесты ещё не отправлялись")
    else:
        lines = [
            "📊 <b>Axela Status</b>",
            "",
            "✅ Bot is running",
            f"📥 Sources: {sources_count}",
            f"⏰ Schedules: {schedules_count}",
        ]
        if last_digest_at:
            lines.append(f"📤 Last digest: {last_digest_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            lines.append("📤 No digests sent yet")

    return "\n".join(lines)
