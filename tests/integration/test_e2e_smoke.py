from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.insights.ports.ai_insight_client import InsightResponse
from app.application.insights.use_cases.process_insight import ProcessInsightUseCase
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.inbound.messaging.insight_consumer import handle_insight_event
from app.inbound.messaging.transaction_consumer import handle_transaction_event
from app.main.config.settings import KafkaSettings
from app.main.insight.refresh_tick import refresh_one_dirty_period
from app.outbound.adapters.redis.consumer_idempotency_store import RedisConsumerIdempotencyStore
from app.outbound.adapters.sqla.insights.work_unit_factory import SqlaInsightWorkUnitFactory
from app.outbound.adapters.sqla.transactions.dirty_period_marker import SqlaDirtyPeriodMarker
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
    """Full pipeline smoke: 5 transactions → outbox → dirty period → chunk refresh
    (mock embedder) → insight requested → outbox → insight processed (mock AI)
    → GET /insights/{id} status=completed."""

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

        # ── 2. Outbox poller: drain TransactionCreated events ───────────────
        publisher1 = _FakePublisher()
        poller1 = OutboxPoller(
            session_factory=session_factory,
            publisher=publisher1,
            topic_map={
                "TransactionCreated": kafka.kafka_topic_transactions,
                "TransactionUpdated": kafka.kafka_topic_transactions,
                "TransactionDeleted": kafka.kafka_topic_transactions,
            },
            batch_size=50,
        )
        sent = await poller1.run_once()
        assert sent >= 5, f"expected >= 5 outbox events, got {sent}"

        # ── 3. Transaction consumer → mark dirty periods ────────────────────
        store1 = RedisConsumerIdempotencyStore(redis=redis)
        for body, _ in publisher1.published:
            if body.get("event_type") == "TransactionCreated":
                async with session_factory.begin() as session:
                    await handle_transaction_event(
                        body,
                        store=store1,
                        dlq_publisher=AsyncMock(),
                        dirty_period_repo=SqlaDirtyPeriodMarker(session),
                        metrics=metrics,
                        dlq_topic=kafka.kafka_topic_dlq,
                        max_retries=3,
                        idempotency_ttl=86400,
                    )

        # ── 4. Refresh dirty period with mock embedder ──────────────────────
        fake_embedder = AsyncMock()
        fake_embedder.embed = AsyncMock(return_value=[0.1] * 1536)
        fake_embedder.embed_batch = AsyncMock(return_value=[[0.1] * 1536])

        did_work = await refresh_one_dirty_period(
            session_factory, fake_embedder, BehavioralShiftDetector()
        )
        assert did_work is True, "dirty_periods queue was empty after consumer step"

        # ── 5. Request insight via HTTP ─────────────────────────────────────
        resp = await client.post(
            "/api/v1/insights/requests",
            json={"period": "monthly", "period_year": 2026, "period_month": 4},
        )
        assert resp.status_code == 202, resp.text
        insight_id = resp.json()["id"]

        # ── 6. Outbox poller: drain InsightRequested event ──────────────────
        publisher2 = _FakePublisher()
        poller2 = OutboxPoller(
            session_factory=session_factory,
            publisher=publisher2,
            topic_map={"InsightRequested": kafka.kafka_topic_insights},
            batch_size=50,
        )
        await poller2.run_once()
        insight_events = [
            b for b, _ in publisher2.published if b.get("event_type") == "InsightRequested"
        ]
        assert insight_events, "no InsightRequested event in outbox"

        # ── 7. Insight consumer: mock AI, run full pipeline ─────────────────
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
            embedder=fake_embedder,
            ai_client=fake_ai,
        )
        store2 = RedisConsumerIdempotencyStore(redis=redis)
        for body in insight_events:
            await handle_insight_event(
                body,
                store=store2,
                dlq_publisher=AsyncMock(),
                process_insight=process_insight,
                metrics=metrics,
                dlq_topic=kafka.kafka_topic_dlq,
                max_retries=3,
                idempotency_ttl=86400,
            )

        # ── 8. Verify insight completed ─────────────────────────────────────
        resp = await client.get(f"/api/v1/insights/{insight_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "completed", f"expected completed, got: {data}"
        assert data["title"] == "April spending review"

    finally:
        await engine.dispose()
        await redis.aclose()
