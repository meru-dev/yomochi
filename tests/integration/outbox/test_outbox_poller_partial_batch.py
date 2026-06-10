import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.outbound.outbox.poller import OutboxPoller
from app.outbound.persistence_sqla.mappings.all import map_tables
from app.outbound.persistence_sqla.mappings.outbox_event import outbox_events

pytestmark = pytest.mark.asyncio


class _PublisherFailingOnNthCall:
    def __init__(self, fail_after_n: int) -> None:
        self._fail_after_n = fail_after_n
        self._calls = 0
        self.published: list[tuple[dict, str]] = []

    async def publish(self, message: dict, topic: str, key: bytes | None = None) -> None:
        self._calls += 1
        if self._calls > self._fail_after_n:
            raise RuntimeError(f"kafka unavailable on call {self._calls}")
        self.published.append((message, topic))


async def _make_session_factory(db_url: str) -> async_sessionmaker[AsyncSession]:
    map_tables()
    engine = create_async_engine(db_url)
    return async_sessionmaker(engine, autoflush=False, expire_on_commit=False)


async def _seed_pending_events(factory, n: int) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    async with factory.begin() as session:
        for _ in range(n):
            result = await session.execute(
                sa.insert(outbox_events)
                .values(
                    event_type="TransactionCreated",
                    aggregate_id=str(uuid.uuid4()),
                    payload={"transaction_date": "2026-05-18"},
                    status="PENDING",
                    occurred_at=datetime.now(UTC),
                    user_id=None,
                )
                .returning(outbox_events.c.id)
            )
            ids.append(result.scalar_one())
    return ids


async def _status_counts(factory, ids: list[uuid.UUID]) -> dict[str, int]:
    async with factory() as session:
        rows = await session.execute(
            sa.select(outbox_events.c.status).where(outbox_events.c.id.in_(ids))
        )
        statuses = [r[0] for r in rows.all()]
    return {s: statuses.count(s) for s in set(statuses)}


async def test_successful_publishes_in_batch_are_not_reverted(pg_url: str) -> None:
    factory = await _make_session_factory(pg_url)
    publisher = _PublisherFailingOnNthCall(fail_after_n=2)  # rows 1, 2 succeed; row 3 fails
    ids = await _seed_pending_events(factory, n=5)

    poller = OutboxPoller(
        session_factory=factory,
        publisher=publisher,
        topic_map={"TransactionCreated": "yomochi.transactions.v1"},
        batch_size=10,
    )

    await poller.run_once()

    # Rows 1, 2 actually went out → must stay SENT on next poll round
    statuses = await _status_counts(factory, ids)
    assert statuses.get("SENT", 0) >= 2, (
        f"expected at least 2 rows SENT (publishes that succeeded), got {statuses}"
    )
    # Row 3 (and after) should remain PENDING — they were never published
    assert statuses.get("PENDING", 0) >= 1


async def test_repeatedly_failing_row_eventually_marked_failed(pg_url: str) -> None:
    """After repeated failures on the same row, it should be marked FAILED so the queue can drain."""
    factory = await _make_session_factory(pg_url)
    ids = await _seed_pending_events(factory, n=1)

    poller = OutboxPoller(
        session_factory=factory,
        publisher=_PublisherFailingOnNthCall(fail_after_n=0),
        topic_map={"TransactionCreated": "yomochi.transactions.v1"},
        batch_size=10,
        max_retries=3,
    )

    for _ in range(10):
        await poller.run_once()

    statuses = await _status_counts(factory, ids)
    assert statuses.get("FAILED", 0) == 1, (
        f"expected the row to be quarantined as FAILED after repeated failure, got {statuses}"
    )
