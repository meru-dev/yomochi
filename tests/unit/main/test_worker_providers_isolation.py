from __future__ import annotations

import pytest
from dishka import make_async_container
from faststream.kafka import KafkaBroker
from redis.asyncio import Redis

from app.application.common.ports.consumer_idempotency_store import ConsumerIdempotencyStore
from app.application.common.ports.event_publisher import EventPublisher
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
    ctx: dict = {
        DatabaseSettings: DatabaseSettings(
            database_url="postgresql+asyncpg://yomochi:yomochi@localhost:5432/yomochi",
            _env_file=None,
        )
    }
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
        # Insight-worker needs the insight chat client + idempotency.
        assert await container.get(AIInsightClient) is not None
        assert await container.get(ConsumerIdempotencyStore) is not None
        assert await container.get(EventPublisher) is not None
    finally:
        await container.close()
