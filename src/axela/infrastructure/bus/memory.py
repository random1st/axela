"""In-memory message bus implementation."""

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog

from axela.domain.events import Event

logger = structlog.get_logger()


class InMemoryMessageBus:
    """In-memory message bus with async event handling.

    This implementation is suitable for single-process deployments.
    For distributed systems, replace with Kafka implementation.
    """

    def __init__(self, max_queue_size: int = 1000) -> None:
        """Initialize the message bus.

        Args:
            max_queue_size: Maximum number of events in the queue.

        """
        self._handlers: dict[type[Event], list[Callable[[Event], Awaitable[None]]]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._worker_task: asyncio.Task[None] | None = None

    def subscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Event], Awaitable[None]],
    ) -> None:
        """Subscribe a handler to an event type.

        Args:
            event_type: The event type to subscribe to.
            handler: Async function to handle the event.

        """
        self._handlers[event_type].append(handler)
        logger.debug(
            "Handler subscribed",
            event_type=event_type.__name__,
            handler=getattr(handler, "__name__", repr(handler)),
        )

    def unsubscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Event], Awaitable[None]],
    ) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: The event type to unsubscribe from.
            handler: The handler to remove.

        """
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug(
                "Handler unsubscribed",
                event_type=event_type.__name__,
                handler=getattr(handler, "__name__", repr(handler)),
            )

    async def publish(self, event: Event) -> None:
        """Publish an event to the bus.

        Args:
            event: The event to publish.

        """
        await self._queue.put(event)
        logger.debug(
            "Event published",
            event_type=type(event).__name__,
            queue_size=self._queue.qsize(),
        )

    async def publish_nowait(self, event: Event) -> bool:
        """Publish an event without waiting if queue is full.

        Args:
            event: The event to publish.

        Returns:
            True if event was published, False if queue was full.

        """
        published = False
        try:
            self._queue.put_nowait(event)
            logger.debug(
                "Event published (nowait)",
                event_type=type(event).__name__,
                queue_size=self._queue.qsize(),
            )
            published = True
        except asyncio.QueueFull:
            logger.warning(
                "Event queue full, event dropped",
                event_type=type(event).__name__,
            )
        return published

    async def _process_event(self, event: Event) -> None:
        """Process a single event by calling all subscribed handlers.

        Args:
            event: The event to process.

        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug("No handlers for event", event_type=event_type.__name__)
            return

        # Run all handlers concurrently
        results = await asyncio.gather(
            *[self._call_handler(handler, event) for handler in handlers],
            return_exceptions=True,
        )

        # Log any errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Handler failed",
                    event_type=event_type.__name__,
                    handler=getattr(handlers[i], "__name__", repr(handlers[i])),
                    error=str(result),
                    exc_info=result,
                )

    async def _call_handler(
        self,
        handler: Callable[[Event], Awaitable[None]],
        event: Event,
    ) -> None:
        """Call a handler with error handling.

        Args:
            handler: The handler to call.
            event: The event to pass to the handler.

        """
        await handler(event)

    async def _worker(self) -> None:
        """Background worker that processes events from the queue."""
        logger.info("Message bus worker started")

        while self._running:
            try:
                # Wait for an event with timeout to allow checking _running flag
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except TimeoutError:
                    continue

                await self._process_event(event)
                self._queue.task_done()

            except asyncio.CancelledError:
                logger.info("Message bus worker cancelled")
                break
            except Exception as e:
                logger.exception("Error in message bus worker", error=str(e), exc_info=e)

        logger.info("Message bus worker stopped")

    async def start(self) -> None:
        """Start the message bus worker."""
        if self._running:
            logger.warning("Message bus already running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Message bus started")

    async def stop(self) -> None:
        """Stop the message bus and wait for pending events."""
        if not self._running:
            return

        self._running = False

        # Wait for queue to be processed
        if not self._queue.empty():
            logger.info(
                "Waiting for pending events",
                pending_count=self._queue.qsize(),
            )
            try:
                await asyncio.wait_for(self._queue.join(), timeout=10.0)
            except TimeoutError:
                logger.warning("Timeout waiting for pending events")

        # Cancel worker task
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

        logger.info("Message bus stopped")

    @property
    def is_running(self) -> bool:
        """Check if the message bus is running."""
        return self._running

    @property
    def queue_size(self) -> int:
        """Get the current queue size."""
        return self._queue.qsize()
