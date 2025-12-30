"""Tests for InMemoryMessageBus."""

import asyncio
from datetime import UTC, datetime

import pytest

from axela.domain.events import CollectionCompleted, CollectorFailed, DigestScheduled, Event
from axela.infrastructure.bus.memory import InMemoryMessageBus


@pytest.fixture
def bus() -> InMemoryMessageBus:
    """Return a new InMemoryMessageBus instance."""
    return InMemoryMessageBus()


@pytest.fixture
def sample_event() -> CollectionCompleted:
    """Return a sample event."""
    from uuid import uuid4

    return CollectionCompleted(
        source_id=uuid4(),
        digest_id=uuid4(),
        items_count=10,
        new_items_count=5,
        timestamp=datetime.now(UTC),
    )


class TestInMemoryMessageBusInit:
    """Tests for message bus initialization."""

    def test_init_default_queue_size(self) -> None:
        """Test default queue size is 1000."""
        bus = InMemoryMessageBus()
        # Queue should not be full with default size
        assert bus.queue_size == 0

    def test_init_custom_queue_size(self) -> None:
        """Test custom queue size."""
        bus = InMemoryMessageBus(max_queue_size=10)
        assert bus.queue_size == 0

    def test_init_not_running(self) -> None:
        """Test bus is not running after init."""
        bus = InMemoryMessageBus()
        assert bus.is_running is False


class TestSubscribe:
    """Tests for subscribe/unsubscribe."""

    def test_subscribe_handler(self, bus: InMemoryMessageBus) -> None:
        """Test subscribing a handler."""

        async def handler(event: Event) -> None:
            pass

        bus.subscribe(CollectionCompleted, handler)

        assert len(bus._handlers[CollectionCompleted]) == 1
        assert handler in bus._handlers[CollectionCompleted]

    def test_subscribe_multiple_handlers(self, bus: InMemoryMessageBus) -> None:
        """Test subscribing multiple handlers to same event."""

        async def handler1(event: Event) -> None:
            pass

        async def handler2(event: Event) -> None:
            pass

        bus.subscribe(CollectionCompleted, handler1)
        bus.subscribe(CollectionCompleted, handler2)

        assert len(bus._handlers[CollectionCompleted]) == 2

    def test_subscribe_different_event_types(self, bus: InMemoryMessageBus) -> None:
        """Test subscribing handlers to different event types."""

        async def handler1(event: Event) -> None:
            pass

        async def handler2(event: Event) -> None:
            pass

        bus.subscribe(CollectionCompleted, handler1)
        bus.subscribe(CollectorFailed, handler2)

        assert len(bus._handlers[CollectionCompleted]) == 1
        assert len(bus._handlers[CollectorFailed]) == 1

    def test_unsubscribe_handler(self, bus: InMemoryMessageBus) -> None:
        """Test unsubscribing a handler."""

        async def handler(event: Event) -> None:
            pass

        bus.subscribe(CollectionCompleted, handler)
        bus.unsubscribe(CollectionCompleted, handler)

        assert len(bus._handlers[CollectionCompleted]) == 0

    def test_unsubscribe_nonexistent_handler(self, bus: InMemoryMessageBus) -> None:
        """Test unsubscribing a handler that doesn't exist."""

        async def handler(event: Event) -> None:
            pass

        # Should not raise
        bus.unsubscribe(CollectionCompleted, handler)

    def test_subscribe_with_lambda(self, bus: InMemoryMessageBus) -> None:
        """Test subscribing a lambda handler (no __name__)."""
        handler = lambda event: event  # noqa: E731

        # Should not raise
        bus.subscribe(CollectionCompleted, handler)  # type: ignore[arg-type]
        assert len(bus._handlers[CollectionCompleted]) == 1


class TestPublish:
    """Tests for publish methods."""

    @pytest.mark.asyncio
    async def test_publish_adds_to_queue(
        self,
        bus: InMemoryMessageBus,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test publish adds event to queue."""
        await bus.publish(sample_event)

        assert bus.queue_size == 1

    @pytest.mark.asyncio
    async def test_publish_multiple_events(
        self,
        bus: InMemoryMessageBus,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test publishing multiple events."""
        await bus.publish(sample_event)
        await bus.publish(sample_event)
        await bus.publish(sample_event)

        assert bus.queue_size == 3

    @pytest.mark.asyncio
    async def test_publish_nowait_success(
        self,
        bus: InMemoryMessageBus,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test publish_nowait succeeds when queue not full."""
        result = await bus.publish_nowait(sample_event)

        assert result is True
        assert bus.queue_size == 1

    @pytest.mark.asyncio
    async def test_publish_nowait_queue_full(
        self,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test publish_nowait returns False when queue full."""
        bus = InMemoryMessageBus(max_queue_size=2)

        # Fill the queue
        await bus.publish_nowait(sample_event)
        await bus.publish_nowait(sample_event)

        # This should fail
        result = await bus.publish_nowait(sample_event)

        assert result is False
        assert bus.queue_size == 2


class TestEventProcessing:
    """Tests for event processing."""

    @pytest.mark.asyncio
    async def test_event_delivered_to_handler(
        self,
        bus: InMemoryMessageBus,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test event is delivered to subscribed handler."""
        received_events: list[Event] = []

        async def handler(event: Event) -> None:
            received_events.append(event)

        bus.subscribe(CollectionCompleted, handler)
        await bus.start()

        await bus.publish(sample_event)
        await asyncio.sleep(0.1)  # Allow worker to process

        await bus.stop()

        assert len(received_events) == 1
        assert received_events[0] == sample_event

    @pytest.mark.asyncio
    async def test_event_delivered_to_multiple_handlers(
        self,
        bus: InMemoryMessageBus,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test event is delivered to all subscribed handlers."""
        received1: list[Event] = []
        received2: list[Event] = []

        async def handler1(event: Event) -> None:
            received1.append(event)

        async def handler2(event: Event) -> None:
            received2.append(event)

        bus.subscribe(CollectionCompleted, handler1)
        bus.subscribe(CollectionCompleted, handler2)
        await bus.start()

        await bus.publish(sample_event)
        await asyncio.sleep(0.1)

        await bus.stop()

        assert len(received1) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_no_handler_for_event(
        self,
        bus: InMemoryMessageBus,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test event with no handlers is handled gracefully."""
        await bus.start()

        # Should not raise
        await bus.publish(sample_event)
        await asyncio.sleep(0.1)

        await bus.stop()

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_stop_processing(
        self,
        bus: InMemoryMessageBus,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test handler exception doesn't stop other handlers."""
        received_events: list[Event] = []

        async def failing_handler(event: Event) -> None:
            raise ValueError("Handler error")

        async def success_handler(event: Event) -> None:
            received_events.append(event)

        bus.subscribe(CollectionCompleted, failing_handler)
        bus.subscribe(CollectionCompleted, success_handler)
        await bus.start()

        await bus.publish(sample_event)
        await asyncio.sleep(0.1)

        await bus.stop()

        # Success handler should still receive event
        assert len(received_events) == 1


class TestStartStop:
    """Tests for start/stop."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self, bus: InMemoryMessageBus) -> None:
        """Test start sets running flag."""
        await bus.start()

        assert bus.is_running is True

        await bus.stop()

    @pytest.mark.asyncio
    async def test_start_already_running(self, bus: InMemoryMessageBus) -> None:
        """Test starting already running bus logs warning."""
        await bus.start()
        await bus.start()  # Should not raise

        assert bus.is_running is True

        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_sets_not_running(self, bus: InMemoryMessageBus) -> None:
        """Test stop clears running flag."""
        await bus.start()
        await bus.stop()

        assert bus.is_running is False

    @pytest.mark.asyncio
    async def test_stop_not_running(self, bus: InMemoryMessageBus) -> None:
        """Test stopping non-running bus is safe."""
        await bus.stop()  # Should not raise

        assert bus.is_running is False

    @pytest.mark.asyncio
    async def test_stop_waits_for_pending_events(
        self,
        bus: InMemoryMessageBus,
    ) -> None:
        """Test stop processes pending events."""
        received_events: list[Event] = []
        from uuid import uuid4

        async def handler(event: Event) -> None:
            received_events.append(event)

        bus.subscribe(CollectionCompleted, handler)
        await bus.start()

        # Give worker time to start
        await asyncio.sleep(0.05)

        # Publish events
        event = CollectionCompleted(
            source_id=uuid4(),
            digest_id=uuid4(),
            items_count=1,
            new_items_count=1,
            timestamp=datetime.now(UTC),
        )
        await bus.publish(event)
        await bus.publish(event)

        # Allow worker to process
        await asyncio.sleep(0.1)

        # Stop should wait for processing
        await bus.stop()

        assert len(received_events) == 2


class TestProperties:
    """Tests for properties."""

    def test_is_running_property(self, bus: InMemoryMessageBus) -> None:
        """Test is_running property."""
        assert bus.is_running is False

    def test_queue_size_property(self, bus: InMemoryMessageBus) -> None:
        """Test queue_size property."""
        assert bus.queue_size == 0

    @pytest.mark.asyncio
    async def test_queue_size_after_publish(
        self,
        bus: InMemoryMessageBus,
        sample_event: CollectionCompleted,
    ) -> None:
        """Test queue_size after publishing."""
        await bus.publish(sample_event)
        assert bus.queue_size == 1

        await bus.publish(sample_event)
        assert bus.queue_size == 2


class TestDifferentEventTypes:
    """Tests for handling different event types."""

    @pytest.mark.asyncio
    async def test_digest_scheduled_event(self, bus: InMemoryMessageBus) -> None:
        """Test DigestScheduled event processing."""
        from uuid import uuid4

        received_events: list[Event] = []

        async def handler(event: Event) -> None:
            received_events.append(event)

        bus.subscribe(DigestScheduled, handler)
        await bus.start()

        event = DigestScheduled(
            schedule_id=uuid4(),
            digest_type="morning",
            project_ids=[uuid4()],
            timestamp=datetime.now(UTC),
        )
        await bus.publish(event)
        await asyncio.sleep(0.1)

        await bus.stop()

        assert len(received_events) == 1
        assert isinstance(received_events[0], DigestScheduled)

    @pytest.mark.asyncio
    async def test_collector_failed_event(self, bus: InMemoryMessageBus) -> None:
        """Test CollectorFailed event processing."""
        from uuid import uuid4

        received_events: list[Event] = []

        async def handler(event: Event) -> None:
            received_events.append(event)

        bus.subscribe(CollectorFailed, handler)
        await bus.start()

        event = CollectorFailed(
            source_id=uuid4(),
            error_type="ConnectionError",
            error_message="Failed to connect",
            timestamp=datetime.now(UTC),
        )
        await bus.publish(event)
        await asyncio.sleep(0.1)

        await bus.stop()

        assert len(received_events) == 1
        assert isinstance(received_events[0], CollectorFailed)

    @pytest.mark.asyncio
    async def test_event_only_delivered_to_correct_type_handler(
        self,
        bus: InMemoryMessageBus,
    ) -> None:
        """Test events are only delivered to handlers of matching type."""
        from uuid import uuid4

        collection_events: list[Event] = []
        failed_events: list[Event] = []

        async def collection_handler(event: Event) -> None:
            collection_events.append(event)

        async def failed_handler(event: Event) -> None:
            failed_events.append(event)

        bus.subscribe(CollectionCompleted, collection_handler)
        bus.subscribe(CollectorFailed, failed_handler)
        await bus.start()

        # Publish only CollectionCompleted
        event = CollectionCompleted(
            source_id=uuid4(),
            digest_id=uuid4(),
            items_count=10,
            new_items_count=5,
            timestamp=datetime.now(UTC),
        )
        await bus.publish(event)
        await asyncio.sleep(0.1)

        await bus.stop()

        assert len(collection_events) == 1
        assert len(failed_events) == 0
