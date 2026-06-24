from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.inbound.messaging._event_id import resolve_event_id
from app.inbound.messaging.insight_consumer import handle_insight_event
from app.outbound.adapters.redis.consumer_idempotency_store import RedisConsumerIdempotencyStore

pytestmark = pytest.mark.asyncio(loop_scope="module")

_DLQ_TOPIC = "yomochi.insights.dlq.v1"
_MAX_RETRIES = 3
_IDEMPOTENCY_TTL = 60


class _RecordingPublisher:
    """EventPublisher recorder — captures payloads so tests can assert contents."""

    def __init__(self) -> None:
        self.published: list[tuple[dict[str, Any], str]] = []

    async def publish(self, message: dict[str, Any], topic: str, key: bytes | None = None) -> None:
        self.published.append((message, topic))


def _make_body() -> dict[str, Any]:
    return {
        "event_id": uuid4().hex,
        "event_type": "InsightRequested",
        "payload": {"insight_id": uuid4().hex, "user_id": uuid4().hex},
    }


async def _drain_loop(
    body: dict[str, Any],
    *,
    store: RedisConsumerIdempotencyStore,
    dlq_publisher: _RecordingPublisher,
    process_insight: AsyncMock,
    metrics: Mock,
) -> None:
    """Drive the handler `max_retries` times: attempts 1..N-1 raise, attempt N parks."""
    for _ in range(_MAX_RETRIES - 1):
        with pytest.raises(RuntimeError):
            await handle_insight_event(
                body,
                store=store,
                dlq_publisher=dlq_publisher,
                process_insight=process_insight,
                metrics=metrics,
                dlq_topic=_DLQ_TOPIC,
                max_retries=_MAX_RETRIES,
                idempotency_ttl=_IDEMPOTENCY_TTL,
            )
        assert dlq_publisher.published == []

    await handle_insight_event(
        body,
        store=store,
        dlq_publisher=dlq_publisher,
        process_insight=process_insight,
        metrics=metrics,
        dlq_topic=_DLQ_TOPIC,
        max_retries=_MAX_RETRIES,
        idempotency_ttl=_IDEMPOTENCY_TTL,
    )


async def test_handler_dlqs_after_max_retries(redis_url: str) -> None:
    """At-least-once with bounded redelivery: same event_id fails `max_retries`
    times across deliveries, then lands in the DLQ exactly once (terminal, no raise)."""
    redis = Redis.from_url(redis_url, decode_responses=False)
    store = RedisConsumerIdempotencyStore(redis)
    dlq_publisher = _RecordingPublisher()
    process_insight = AsyncMock(side_effect=RuntimeError("boom"))
    metrics = Mock()
    body = _make_body()

    try:
        await _drain_loop(
            body,
            store=store,
            dlq_publisher=dlq_publisher,
            process_insight=process_insight,
            metrics=metrics,
        )

        assert len(dlq_publisher.published) == 1
        message, topic = dlq_publisher.published[0]
        assert topic == _DLQ_TOPIC
        assert message["event_id"] == body["event_id"]
        assert message["payload"] == body["payload"]
        assert "x_error" in message
        assert "boom" in message["x_error"]
        metrics.consumer_dlq_event.assert_called_once()
    finally:
        await redis.aclose()


async def test_no_double_dlq_on_redelivery_after_park(redis_url: str) -> None:
    """Once parked, a further redelivery short-circuits on is_processed and never
    publishes a second DLQ message."""
    redis = Redis.from_url(redis_url, decode_responses=False)
    store = RedisConsumerIdempotencyStore(redis)
    dlq_publisher = _RecordingPublisher()
    process_insight = AsyncMock(side_effect=RuntimeError("boom"))
    metrics = Mock()
    body = _make_body()

    try:
        await _drain_loop(
            body,
            store=store,
            dlq_publisher=dlq_publisher,
            process_insight=process_insight,
            metrics=metrics,
        )
        assert len(dlq_publisher.published) == 1

        # N+1 redelivery: must return cleanly via idempotency short-circuit.
        await handle_insight_event(
            body,
            store=store,
            dlq_publisher=dlq_publisher,
            process_insight=process_insight,
            metrics=metrics,
            dlq_topic=_DLQ_TOPIC,
            max_retries=_MAX_RETRIES,
            idempotency_ttl=_IDEMPOTENCY_TTL,
        )

        assert len(dlq_publisher.published) == 1
    finally:
        await redis.aclose()


async def test_success_path_marks_processed_without_dlq(redis_url: str) -> None:
    """Clean handler run marks the event processed and never touches the DLQ."""
    redis = Redis.from_url(redis_url, decode_responses=False)
    store = RedisConsumerIdempotencyStore(redis)
    dlq_publisher = _RecordingPublisher()
    process_insight = AsyncMock()
    metrics = Mock()
    body = _make_body()

    try:
        await handle_insight_event(
            body,
            store=store,
            dlq_publisher=dlq_publisher,
            process_insight=process_insight,
            metrics=metrics,
            dlq_topic=_DLQ_TOPIC,
            max_retries=_MAX_RETRIES,
            idempotency_ttl=_IDEMPOTENCY_TTL,
        )

        assert dlq_publisher.published == []
        assert await store.is_processed(resolve_event_id(body)) is True
    finally:
        await redis.aclose()
