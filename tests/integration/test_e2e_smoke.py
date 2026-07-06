from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.insights.ports.ai_insight_client import InsightResponse
from app.application.insights.use_cases.process_insight import ProcessInsightUseCase
from app.inbound.messaging.insight_consumer import handle_insight_event
from app.main.config.settings import KafkaSettings
from app.outbound.adapters.redis.consumer_idempotency_store import RedisConsumerIdempotencyStore
from app.outbound.adapters.sqla.insights.work_unit_factory import SqlaInsightWorkUnitFactory
from app.outbound.outbox.poller import OutboxPoller
from tests.integration.factories import create_transaction, register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")


class _FakeMetrics:
    def consumer_idempotency_skip(self, topic: str) -> None: ...
    def consumer_dlq_event(self, topic: str) -> None: ...
    def insight_generation_observed(self, context_quality: str, seconds: float) -> None: ...


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[dict, str]] = []

    async def publish(self, message: dict, topic: str, key: bytes | None = None) -> None:
        self.published.append((message, topic))


async def test_e2e_tx_to_insight_completed(
    client: AsyncClient,
    integration_settings: dict,
    redis_url: str,
) -> None:
    """Full pipeline smoke: 5 transactions → insight requested → outbox drain
    → insight processed (deterministic context from SQL, mock AI)
    → GET /insights/{id} status=completed.

    The embedding/chunk-refresh subsystem was removed (arch-simplification
    task 5b): process_insight now builds its context deterministically by reading
    the period's transactions straight from SQL — no embedder, no chunk store.
    """

    db_url = integration_settings["database_settings"].database_url
    redis = Redis.from_url(redis_url)

    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)
    kafka = KafkaSettings()
    metrics = _FakeMetrics()

    try:
        # ── 1. Register + create 5 transactions in April 2026 ──────────────
        await register_and_login(client, email="e2e-smoke@example.com")
        for i in range(5):
            await create_transaction(client, date=f"2026-04-{i + 1:02d}", merchant="Lawson")

        # ── 2. Request insight via HTTP ─────────────────────────────────────
        resp = await client.post(
            "/api/v1/insights/requests",
            json={"period": "monthly", "period_year": 2026, "period_month": 4},
        )
        assert resp.status_code == 202, resp.text
        insight_id = resp.json()["id"]

        # ── 3. Outbox poller: drain InsightRequested event ──────────────────
        publisher = _FakePublisher()
        poller = OutboxPoller(
            session_factory=session_factory,
            publisher=publisher,
            topic_map={"InsightRequested": kafka.kafka_topic_insights},
            batch_size=50,
        )
        await poller.run_once()
        insight_events = [
            b for b, _ in publisher.published if b.get("event_type") == "InsightRequested"
        ]
        assert insight_events, "no InsightRequested event in outbox"

        # ── 4. Insight consumer: mock AI, run full pipeline ─────────────────
        fake_ai = AsyncMock()
        fake_ai.generate = AsyncMock(
            return_value=InsightResponse(
                title="April spending review",
                description="Most spending was at Lawson convenience stores.",
                impact_score=5,
                prompt_tokens=200,
                completion_tokens=80,
            )
        )

        process_insight = ProcessInsightUseCase(
            work_unit_factory=SqlaInsightWorkUnitFactory(session_factory),
            ai_client=fake_ai,
        )
        store = RedisConsumerIdempotencyStore(redis=redis)
        for body in insight_events:
            await handle_insight_event(
                body,
                store=store,
                dlq_publisher=AsyncMock(),
                process_insight=process_insight,
                metrics=metrics,
                dlq_topic=kafka.kafka_topic_dlq,
                max_retries=3,
                idempotency_ttl=86400,
            )

        # ── 5. Verify insight completed ─────────────────────────────────────
        resp = await client.get(f"/api/v1/insights/{insight_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "completed", f"expected completed, got: {data}"
        assert data["title"] == "April spending review"

    finally:
        await engine.dispose()
        await redis.aclose()
