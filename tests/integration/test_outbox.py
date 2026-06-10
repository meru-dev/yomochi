import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.inbound.messaging.transaction_consumer import handle_transaction_event
from app.main.config.settings import KafkaSettings
from app.outbound.adapters.redis.consumer_idempotency_store import RedisConsumerIdempotencyStore
from app.outbound.outbox.poller import OutboxPoller
from app.outbound.persistence_sqla.mappings.outbox_event import outbox_events
from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")


class _FakeMetrics:
    def consumer_idempotency_skip(self, topic: str) -> None: ...
    def consumer_dlq_event(self, topic: str) -> None: ...
    def insight_generation_observed(self, context_quality: str, seconds: float) -> None: ...


class FakeEventPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[dict, str]] = []

    async def publish(self, message: dict, topic: str, key: bytes | None = None) -> None:
        self.published.append((message, topic))


class FakeDirtyPeriodRepo:
    async def mark_dirty(self, user_id, year: int, month: int) -> None:
        pass

    async def pop_dirty(self, limit: int = 100) -> list:
        return []


async def test_outbox_relay_publishes_and_marks_sent(
    client: AsyncClient,
    integration_settings: dict,
) -> None:
    """POST /transactions → outbox row PENDING → poller runs → row SENT, event published."""
    await register_and_login(client)

    resp = await client.post(
        "/api/v1/transactions",
        json={"amount": "25.00", "currency": "USD", "date": "2026-05-18", "type": "expense"},
    )
    assert resp.status_code == 201, resp.text

    engine = create_async_engine(integration_settings["database_settings"].database_url)
    session_factory = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)
    publisher = FakeEventPublisher()
    kafka_cfg = KafkaSettings()

    poller = OutboxPoller(
        session_factory=session_factory,
        publisher=publisher,
        topic_map={
            "TransactionCreated": kafka_cfg.kafka_topic_transactions,
            "TransactionUpdated": kafka_cfg.kafka_topic_transactions,
            "TransactionDeleted": kafka_cfg.kafka_topic_transactions,
        },
        batch_size=10,
    )

    sent = await poller.run_once()
    await engine.dispose()

    assert sent >= 1
    assert any(m["event_type"] == "TransactionCreated" for m, _ in publisher.published)

    # Verify DB status
    engine2 = create_async_engine(integration_settings["database_settings"].database_url)
    try:
        async with async_sessionmaker(engine2)() as session:
            result = await session.execute(
                sa.select(outbox_events.c.status).where(outbox_events.c.status == "SENT")
            )
            rows = result.scalars().all()
    finally:
        await engine2.dispose()
    assert len(rows) >= 1


async def test_consumer_idempotency_skips_duplicate(
    integration_settings: dict,
    redis_url: str,
) -> None:
    """Same event_id processed twice → second call is a no-op."""
    redis_client = Redis.from_url(redis_url)

    store = RedisConsumerIdempotencyStore(redis=redis_client)
    publisher = FakeEventPublisher()
    kafka_cfg = KafkaSettings()
    event_id = str(uuid.uuid4())
    body = {
        "event_id": event_id,
        "event_type": "TransactionCreated",
        "aggregate_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "payload": {},
        "occurred_at": datetime.now(UTC).isoformat(),
    }

    await handle_transaction_event(
        body,
        store=store,
        dlq_publisher=publisher,
        dirty_period_repo=FakeDirtyPeriodRepo(),
        metrics=_FakeMetrics(),
        dlq_topic=kafka_cfg.kafka_topic_dlq,
        max_retries=kafka_cfg.consumer_max_retries,
        idempotency_ttl=kafka_cfg.consumer_idempotency_ttl_seconds,
    )
    # Second call — must be skipped
    await handle_transaction_event(
        body,
        store=store,
        dlq_publisher=publisher,
        dirty_period_repo=FakeDirtyPeriodRepo(),
        metrics=_FakeMetrics(),
        dlq_topic=kafka_cfg.kafka_topic_dlq,
        max_retries=kafka_cfg.consumer_max_retries,
        idempotency_ttl=kafka_cfg.consumer_idempotency_ttl_seconds,
    )

    assert len(publisher.published) == 0  # no DLQ events
    assert await store.is_processed(event_id)

    await redis_client.aclose()
