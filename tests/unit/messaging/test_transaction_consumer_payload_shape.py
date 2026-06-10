import uuid

import pytest

from app.inbound.messaging.transaction_consumer import handle_transaction_event

pytestmark = pytest.mark.asyncio


class _FakeStore:
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


class _FakeDlqPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[dict, str]] = []

    async def publish(self, message: dict, topic: str, key: bytes | None = None) -> None:
        self.published.append((message, topic))


class _FakeDirtyRepo:
    def __init__(self) -> None:
        self.marked: list[tuple] = []

    async def mark_dirty(self, user_id, year: int, month: int) -> None:
        self.marked.append((user_id, year, month))

    async def pop_dirty(self, limit: int = 100):
        return []


class _FakeMetrics:
    def consumer_idempotency_skip(self, topic: str) -> None: ...
    def consumer_dlq_event(self, topic: str) -> None: ...
    def insight_generation_observed(self, *args, **kwargs) -> None: ...


def _outbox_shaped_event(user_id: str, tx_date: str, *, old_date: str | None = None) -> dict:
    """Mirrors OutboxPoller._publish_row exactly."""
    payload: dict = {"transaction_date": tx_date}
    if old_date is not None:
        payload["old_date"] = old_date
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "TransactionCreated",
        "aggregate_id": str(uuid.uuid4()),
        "user_id": user_id,
        "payload": payload,
        "occurred_at": "2026-05-18T00:00:00+00:00",
    }


async def test_consumer_marks_dirty_period_from_payload_shaped_body() -> None:
    """The producer puts transaction_date inside `payload`. The consumer must read it from there."""
    store = _FakeStore()
    dlq = _FakeDlqPublisher()
    dirty = _FakeDirtyRepo()
    user_id_str = str(uuid.uuid4())
    body = _outbox_shaped_event(user_id_str, tx_date="2026-03-15")

    await handle_transaction_event(
        body,
        store=store,
        dlq_publisher=dlq,
        dirty_period_repo=dirty,
        metrics=_FakeMetrics(),
        dlq_topic="dlq",
        max_retries=3,
        idempotency_ttl=86400,
    )

    assert len(dirty.marked) == 1
    _, year, month = dirty.marked[0]
    assert year == 2026
    assert month == 3


async def test_consumer_marks_both_periods_on_update_with_date_change() -> None:
    """TransactionUpdated with date moved across months → both old and new month marked dirty."""
    store = _FakeStore()
    dlq = _FakeDlqPublisher()
    dirty = _FakeDirtyRepo()
    user_id_str = str(uuid.uuid4())
    body = _outbox_shaped_event(user_id_str, tx_date="2026-04-02", old_date="2026-03-30")
    body["event_type"] = "TransactionUpdated"

    await handle_transaction_event(
        body,
        store=store,
        dlq_publisher=dlq,
        dirty_period_repo=dirty,
        metrics=_FakeMetrics(),
        dlq_topic="dlq",
        max_retries=3,
        idempotency_ttl=86400,
    )

    months_marked = {(year, month) for _, year, month in dirty.marked}
    assert (2026, 4) in months_marked
    assert (2026, 3) in months_marked
