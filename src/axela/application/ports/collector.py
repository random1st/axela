"""Collector protocol definition."""

from datetime import datetime
from typing import Any, Protocol

from axela.domain.enums import SourceType
from axela.domain.models import DigestItem


class Collector(Protocol):
    """Protocol for data source collectors.

    Each collector is responsible for fetching data from a specific
    source type (Jira, Gmail, Slack, etc.) and converting it to
    DigestItem objects.
    """

    @property
    def source_type(self) -> SourceType:
        """The type of source this collector handles."""
        ...

    async def collect(
        self,
        source_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any],
        since: datetime | None = None,
    ) -> list[DigestItem]:
        """Collect items from the source.

        Args:
            source_id: Unique identifier for the source.
            credentials: Authentication credentials for the source.
            config: Source-specific configuration.
            since: Only fetch items updated after this time.
                   If None, fetches based on initial_fetch_days setting.

        Returns:
            List of DigestItem objects.

        Raises:
            CollectorError: If collection fails.

        """
        ...

    async def validate_credentials(
        self,
        credentials: dict[str, Any],
    ) -> bool:
        """Validate that credentials are correct and have required permissions.

        Args:
            credentials: Authentication credentials to validate.

        Returns:
            True if credentials are valid, False otherwise.

        """
        ...


class CollectorError(Exception):
    """Base exception for collector errors."""

    def __init__(
        self,
        message: str,
        error_type: str = "unknown",
        *,
        recoverable: bool = True,
    ) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error message.
            error_type: Type of error (auth, rate_limit, network, etc.).
            recoverable: Whether the error is recoverable with retry.

        """
        super().__init__(message)
        self.error_type = error_type
        self.recoverable = recoverable


class AuthenticationError(CollectorError):
    """Authentication failed - credentials are invalid or expired."""

    def __init__(self, message: str = "Authentication failed") -> None:
        """Initialize authentication error."""
        super().__init__(message, error_type="auth", recoverable=False)


class RateLimitError(CollectorError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
    ) -> None:
        """Initialize rate limit error."""
        super().__init__(message, error_type="rate_limit", recoverable=True)
        self.retry_after = retry_after


class NetworkError(CollectorError):
    """Network error - connection failed."""

    def __init__(self, message: str = "Network error") -> None:
        """Initialize network error."""
        super().__init__(message, error_type="network", recoverable=True)


class ConfigurationError(CollectorError):
    """Configuration error - invalid config."""

    def __init__(self, message: str = "Invalid configuration") -> None:
        """Initialize configuration error."""
        super().__init__(message, error_type="config", recoverable=False)
