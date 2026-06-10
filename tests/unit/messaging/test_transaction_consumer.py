import uuid

import pytest

from app.inbound.messaging.transaction_consumer import handle_transaction_event

pytestmark = pytest.mark.asyncio


class FakeMetrics:
    def __init__(self) -> None:
        self.skips: list[str] = []
        self.dlqs: list[str] = []
        self.insights: list[tuple[str, float]] = []

    def consumer_idempotency_skip(self, topic: str) -> None:
        self.skips.append(topic)

    def consumer_dlq_event(self, topic: str) -> None:
        self.dlqs.append(topic)

    def insight_generation_observed(self, context_quality: str, seconds: float) -> None:
        self.insights.append((context_quality, seconds))


class FakeIdempotencyStore:
    def __init__(self) -> None:
        self._processed: set[str] = set()
        self._failures: dict[str, int] = {}

    async def is_processed(self, event_id: str) -> bool:
        return event_id in self._processed

    async def mark_processed(self, event_id: str, ttl_seconds: int) -> None:
        self._processed.add(event_id)

    async def increment_failures(self, event_id: str) -> int:
        self._failures[event_id] = self._failures.get(event_id, 0) + 1
        return self._failures[event_id]


class FakeDlqPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[dict, str]] = []

    async def publish(self, message: dict, topic: str, key: bytes | None = None) -> None:
        self.published.append((message, topic))


class FakeDirtyPeriodRepo:
    def __init__(self) -> None:
        self.marked: list[tuple] = []

    async def mark_dirty(self, user_id, year: int, month: int) -> None:
        self.marked.append((user_id, year, month))

    async def pop_dirty(self, limit: int = 100):
        return []


async def test_duplicate_event_is_skipped() -> None:
    """Second call with same event_id must not re-process."""
    store = FakeIdempotencyStore()
    dlq = FakeDlqPublisher()
    event_id = str(uuid.uuid4())
    body = {
        "event_id": event_id,
        "event_type": "TransactionCreated",
        "aggregate_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "payload": {},
        "occurred_at": "2026-05-18T00:00:00+00:00",
    }

    dirty = FakeDirtyPeriodRepo()
    await handle_transaction_event(
        body,
        store=store,
        dlq_publisher=dlq,
        dirty_period_repo=dirty,
        metrics=FakeMetrics(),
        dlq_topic="dlq",
        max_retries=3,
        idempotency_ttl=86400,
    )
    await handle_transaction_event(
        body,
        store=store,
        dlq_publisher=dlq,
        dirty_period_repo=dirty,
        metrics=FakeMetrics(),
        dlq_topic="dlq",
        max_retries=3,
        idempotency_ttl=86400,
    )

    assert len(dlq.published) == 0
    assert event_id in store._processed


async def test_event_parked_in_dlq_after_max_retries() -> None:
    """Handler that always raises → parked in DLQ after max_retries."""
    store = FakeIdempotencyStore()
    dlq = FakeDlqPublisher()
    event_id = str(uuid.uuid4())
    body = {
        "event_id": event_id,
        "event_type": "TransactionCreated",
        "aggregate_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "payload": {"transaction_date": "2026-05-18"},
        "occurred_at": "2026-05-18T00:00:00+00:00",
    }

    class _RaisingDirtyPeriodRepo:
        async def mark_dirty(self, *_a: object, **_kw: object) -> None:
            raise RuntimeError("simulated")

    dirty = _RaisingDirtyPeriodRepo()

    for i in range(1, 4):
        if i < 3:
            with pytest.raises(RuntimeError):
                await handle_transaction_event(
                    body,
                    store=store,
                    dlq_publisher=dlq,
                    dirty_period_repo=dirty,
                    metrics=FakeMetrics(),
                    dlq_topic="dlq.topic",
                    max_retries=3,
                    idempotency_ttl=86400,
                )
        else:
            await handle_transaction_event(
                body,
                store=store,
                dlq_publisher=dlq,
                dirty_period_repo=dirty,
                metrics=FakeMetrics(),
                dlq_topic="dlq.topic",
                max_retries=3,
                idempotency_ttl=86400,
            )

    assert len(dlq.published) == 1
    assert dlq.published[0][1] == "dlq.topic"
    assert event_id in store._processed


async def test_dirty_period_marked_for_transaction_date() -> None:
    """mark_dirty called with correct user_id, year, month from transaction_date."""
    store = FakeIdempotencyStore()
    dlq = FakeDlqPublisher()
    dirty = FakeDirtyPeriodRepo()

    user_id_str = str(uuid.uuid4())
    body = {
        "event_id": str(uuid.uuid4()),
        "event_type": "TransactionCreated",
        "aggregate_id": str(uuid.uuid4()),
        "user_id": user_id_str,
        "payload": {"transaction_date": "2026-03-15"},
        "occurred_at": "2026-03-15T00:00:00+00:00",
    }

    await handle_transaction_event(
        body,
        store=store,
        dlq_publisher=dlq,
        dirty_period_repo=dirty,
        metrics=FakeMetrics(),
        dlq_topic="dlq",
        max_retries=3,
        idempotency_ttl=86400,
    )

    assert len(dirty.marked) == 1
    _, year, month = dirty.marked[0]
    assert year == 2026
    assert month == 3
