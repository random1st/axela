"""Domain enumerations."""

from enum import StrEnum


class SourceType(StrEnum):
    """Types of data sources."""

    JIRA = "jira"
    GMAIL = "gmail"
    GOOGLE_CALENDAR = "google_calendar"
    SLACK = "slack"
    OUTLOOK_MAIL = "outlook_mail"
    OUTLOOK_CALENDAR = "outlook_calendar"
    TEAMS = "teams"


class DigestType(StrEnum):
    """Types of digests."""

    MORNING = "morning"
    EVENING = "evening"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"


class ItemType(StrEnum):
    """Types of items from sources."""

    # Jira
    ISSUE = "issue"
    COMMENT = "comment"

    # Email
    EMAIL = "email"

    # Calendar
    EVENT = "event"

    # Messaging
    MESSAGE = "message"
    THREAD_REPLY = "thread_reply"
    MENTION = "mention"


class DigestStatus(StrEnum):
    """Status of a digest."""

    PENDING = "pending"
    COLLECTING = "collecting"
    FORMATTING = "formatting"
    SENT = "sent"
    FAILED = "failed"
