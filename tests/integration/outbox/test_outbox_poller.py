import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.outbound.outbox.poller import OutboxPoller
from app.outbound.persistence_sqla.mappings.all import map_tables
from app.outbound.persistence_sqla.mappings.outbox_event import outbox_events

pytestmark = pytest.mark.asyncio


class FakeEventPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[dict, str]] = []
        self.should_fail: bool = False

    async def publish(self, message: dict, topic: str, key: bytes | None = None) -> None:
        if self.should_fail:
            raise RuntimeError("kafka unavailable")
        self.published.append((message, topic))


async def _make_session_factory(db_url: str) -> async_sessionmaker[AsyncSession]:
    map_tables()
    engine = create_async_engine(db_url)
    return async_sessionmaker(engine, autoflush=False, expire_on_commit=False)


async def test_poller_marks_event_sent(pg_url: str) -> None:
    """Happy path: PENDING event is published and marked SENT."""
    factory = await _make_session_factory(pg_url)
    publisher = FakeEventPublisher()

    async with factory.begin() as session:
        await session.execute(sa.text("TRUNCATE outbox_events"))

    event_id: uuid.UUID

    async with factory.begin() as session:
        result = await session.execute(
            sa.insert(outbox_events)
            .values(
                event_type="TransactionCreated",
                aggregate_id=str(uuid.uuid4()),
                payload={},
                status="PENDING",
                occurred_at=datetime.now(UTC),
                user_id=None,  # nullable; no users row needed
            )
            .returning(outbox_events.c.id)
        )
        event_id = result.scalar_one()

    poller = OutboxPoller(
        session_factory=factory,
        publisher=publisher,
        topic_map={"TransactionCreated": "yomochi.transactions.v1"},
        batch_size=10,
    )
    processed = await poller.run_once()

    assert processed == 1
    assert len(publisher.published) == 1
    msg, topic = publisher.published[0]
    assert msg["event_type"] == "TransactionCreated"
    assert msg["event_id"] == str(event_id)
    assert topic == "yomochi.transactions.v1"

    async with factory() as session:
        row = await session.execute(
            sa.select(outbox_events.c.status).where(outbox_events.c.id == event_id)
        )
        assert row.scalar_one() == "SENT"


async def test_poller_leaves_pending_on_kafka_failure(pg_url: str) -> None:
    """If publish raises, the row stays PENDING for the next cycle."""
    factory = await _make_session_factory(pg_url)
    publisher = FakeEventPublisher()
    publisher.should_fail = True

    async with factory.begin() as session:
        await session.execute(sa.text("TRUNCATE outbox_events"))

    event_id: uuid.UUID

    async with factory.begin() as session:
        result = await session.execute(
            sa.insert(outbox_events)
            .values(
                event_type="TransactionCreated",
                aggregate_id=str(uuid.uuid4()),
                payload={},
                status="PENDING",
                occurred_at=datetime.now(UTC),
                user_id=None,  # nullable; no users row needed
            )
            .returning(outbox_events.c.id)
        )
        event_id = result.scalar_one()

    poller = OutboxPoller(
        session_factory=factory,
        publisher=publisher,
        topic_map={"TransactionCreated": "yomochi.transactions.v1"},
        batch_size=10,
    )
    processed = await poller.run_once()

    assert processed == 0
    async with factory() as session:
        row = await session.execute(
            sa.select(outbox_events.c.status).where(outbox_events.c.id == event_id)
        )
        assert row.scalar_one() == "PENDING"
