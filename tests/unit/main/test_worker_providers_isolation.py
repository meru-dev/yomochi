from __future__ import annotations

import pytest
from dishka import make_async_container
from dishka.exceptions import NoFactoryError
from faststream.kafka import KafkaBroker
from redis.asyncio import Redis

from app.application.common.ports.consumer_idempotency_store import ConsumerIdempotencyStore
from app.application.common.ports.event_publisher import EventPublisher
from app.application.common.ports.metrics_recorder import MetricsRecorder
from app.application.common.ports.text_embedder import TextEmbedder
from app.application.insights.ports.ai_insight_client import AIInsightClient
from app.main.config.settings import (
    DatabaseSettings,
    InsightWorkerSettings,
    KafkaSettings,
    OpenAISettings,
    RedisSettings,
)
from app.main.ioc.worker_providers import (
    InsightPersistenceProvider,
    InsightUseCasesProvider,
    PortraitAdaptersProvider,
    TransactionPersistenceProvider,
    WorkerAdaptersBaseProvider,
    WorkerAdaptersInsightProvider,
    WorkerInfraProvider,
)

pytestmark = pytest.mark.asyncio


def _context(
    *,
    include_redis: bool = True,
    include_kafka: bool = True,
    include_openai: bool = True,
) -> dict:
    ctx: dict = {DatabaseSettings: DatabaseSettings(_env_file=None)}
    if include_redis:
        ctx[RedisSettings] = RedisSettings(_env_file=None)
        ctx[Redis] = Redis.from_url("redis://localhost:6379/0")
    if include_kafka:
        ctx[KafkaSettings] = KafkaSettings(_env_file=None)
        ctx[KafkaBroker] = KafkaBroker(bootstrap_servers="localhost:9092")
    if include_openai:
        ctx[OpenAISettings] = OpenAISettings(_env_file=None)
        ctx[InsightWorkerSettings] = InsightWorkerSettings(_env_file=None)
    return ctx


# --- transaction-worker ----------------------------------------------------


async def test_transaction_worker_resolves_required_ports() -> None:
    container = make_async_container(
        WorkerInfraProvider(),
        WorkerAdaptersBaseProvider(),
        TransactionPersistenceProvider(),
        context=_context(include_openai=False),
    )
    try:
        # APP-scoped — handler depends on these.
        assert await container.get(ConsumerIdempotencyStore) is not None
        assert await container.get(EventPublisher) is not None
        assert await container.get(MetricsRecorder) is not None
    finally:
        await container.close()


async def test_transaction_worker_rejects_ai_insight_client() -> None:
    """transaction-worker MUST NOT have access to OpenAI chat client.

    This is the bulkhead invariant: an outage on the chat endpoint cannot
    open the circuit breaker for tx indexing because tx-worker never holds
    a reference to that client.
    """
    container = make_async_container(
        WorkerInfraProvider(),
        WorkerAdaptersBaseProvider(),
        TransactionPersistenceProvider(),
        context=_context(include_openai=False),
    )
    try:
        with pytest.raises(NoFactoryError):
            await container.get(AIInsightClient)
        with pytest.raises(NoFactoryError):
            await container.get(TextEmbedder)
    finally:
        await container.close()


# --- insight-worker --------------------------------------------------------


async def test_insight_worker_resolves_required_ports() -> None:
    container = make_async_container(
        WorkerInfraProvider(),
        WorkerAdaptersBaseProvider(),
        WorkerAdaptersInsightProvider(),
        InsightPersistenceProvider(),
        InsightUseCasesProvider(),
        context=_context(),
    )
    try:
        # Insight-worker needs the full OpenAI stack + idempotency.
        assert await container.get(AIInsightClient) is not None
        assert await container.get(TextEmbedder) is not None
        assert await container.get(ConsumerIdempotencyStore) is not None
        assert await container.get(EventPublisher) is not None
    finally:
        await container.close()


# --- portrait-worker -------------------------------------------------------


async def test_portrait_worker_resolves_embedder_only() -> None:
    """Portrait only needs the embedder. Chat client is intentionally absent —
    portraits never call the chat model, so the breaker on chat is irrelevant.
    """
    container = make_async_container(
        WorkerInfraProvider(),
        PortraitAdaptersProvider(),
        context=_context(include_redis=False, include_kafka=False),
    )
    try:
        assert await container.get(TextEmbedder) is not None
    finally:
        await container.close()


async def test_portrait_worker_rejects_kafka_and_chat() -> None:
    container = make_async_container(
        WorkerInfraProvider(),
        PortraitAdaptersProvider(),
        context=_context(include_redis=False, include_kafka=False),
    )
    try:
        with pytest.raises(NoFactoryError):
            await container.get(AIInsightClient)
        with pytest.raises(NoFactoryError):
            await container.get(ConsumerIdempotencyStore)
        with pytest.raises(NoFactoryError):
            await container.get(EventPublisher)
    finally:
        await container.close()
