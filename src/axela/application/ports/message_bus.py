"""Message bus protocol definition."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from axela.domain.events import Event


class MessageBus(Protocol):
    """Protocol for message bus implementations."""

    async def publish(self, event: Event) -> None:
        """Publish an event to the bus."""
        ...

    def subscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Event], Awaitable[None]],
    ) -> None:
        """Subscribe a handler to an event type."""
        ...

    async def start(self) -> None:
        """Start the message bus."""
        ...

    async def stop(self) -> None:
        """Stop the message bus and clean up resources."""
        ...
