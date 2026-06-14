import asyncio
from typing import Any

import redis.asyncio as aioredis
import structlog
from dishka import make_async_container
from dishka_faststream import FromDishka, setup_dishka
from faststream import AckPolicy, Context, FastStream
from faststream.kafka import KafkaBroker
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.common.ports.consumer_idempotency_store import ConsumerIdempotencyStore
from app.application.common.ports.event_publisher import EventPublisher
from app.application.common.ports.metrics_recorder import MetricsRecorder
from app.application.common.ports.text_embedder import TextEmbedder
from app.application.insights.use_cases.process_insight import ProcessInsightUseCase
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.inbound.messaging.insight_consumer import handle_insight_event
from app.main.config.loader import (
    load_database_settings,
    load_kafka_settings,
    load_observability_settings,
    load_openai_settings,
    load_redis_settings,
)
from app.main.config.settings import (
    DatabaseSettings,
    KafkaSettings,
    ObservabilitySettings,
    OpenAISettings,
    RedisSettings,
)
from app.main.insight.refresh_tick import refresh_one_dirty_period
from app.main.ioc.worker_providers import (
    InsightPersistenceProvider,
    InsightUseCasesProvider,
    WorkerAdaptersBaseProvider,
    WorkerAdaptersInsightProvider,
    WorkerInfraProvider,
)
from app.main.logging import configure_logging
from app.outbound.observability.otel import configure_otel
from app.outbound.observability.propagation import extract_context
from app.outbound.persistence_sqla.mappings.all import map_tables

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_CONSUMER_GROUP = "insight-worker"
_REFRESH_INTERVAL_SECONDS = 30
_REFRESH_BATCH_SIZE = 20
_REFRESH_CONCURRENCY = 4  # concurrent OpenAI embedding calls per tick


async def _refresh_one_period_safe(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: TextEmbedder,
    detector: BehavioralShiftDetector,
    sem: asyncio.Semaphore,
) -> bool:
    async with sem:
        try:
            return await refresh_one_dirty_period(session_factory, embedder, detector)
        except Exception:
            logger.exception("embedding_refresh_period_error")
            return False


async def _embedding_refresh_loop(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: TextEmbedder,
    detector: BehavioralShiftDetector,
) -> None:
    sem = asyncio.Semaphore(_REFRESH_CONCURRENCY)
    while True:
        await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
        results = await asyncio.gather(
            *[
                _refresh_one_period_safe(session_factory, embedder, detector, sem)
                for _ in range(_REFRESH_BATCH_SIZE)
            ],
            return_exceptions=True,
        )
        # The per-task wrapper catches Exception; this guards BaseException /
        # cancellation leaks that gather would otherwise discard silently.
        for r in results:
            if isinstance(r, BaseException):
                logger.error("embedding_refresh_task_error", exc_info=r)
        processed = sum(1 for r in results if r is True)
        if processed:
            logger.info("embedding_refresh_tick", processed=processed)


def make_app(
    db_settings: DatabaseSettings | None = None,
    redis_settings: RedisSettings | None = None,
    openai_settings: OpenAISettings | None = None,
    kafka_settings: KafkaSettings | None = None,
    obs_settings: ObservabilitySettings | None = None,
) -> FastStream:
    db_cfg = db_settings or load_database_settings()
    redis_cfg = redis_settings or load_redis_settings()
    openai_cfg = openai_settings or load_openai_settings()
    kafka_cfg = kafka_settings or load_kafka_settings()
    obs_cfg = obs_settings or load_observability_settings()

    map_tables()
    configure_logging(log_format=obs_cfg.log_format, debug=False)
    configure_otel(
        service_name="yomochi-insight-worker",
        otlp_endpoint=obs_cfg.otel_exporter_otlp_endpoint,
        enabled=obs_cfg.otel_enabled,
    )

    if obs_cfg.otel_enabled:
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()

    broker = KafkaBroker(bootstrap_servers=kafka_cfg.kafka_bootstrap_servers)
    redis_client: Redis = aioredis.from_url(  # type: ignore[type-arg]
        redis_cfg.redis_url,
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
        health_check_interval=30,
    )

    container = make_async_container(
        WorkerInfraProvider(),
        WorkerAdaptersBaseProvider(),
        WorkerAdaptersInsightProvider(),
        InsightPersistenceProvider(),
        InsightUseCasesProvider(),
        context={
            DatabaseSettings: db_cfg,
            OpenAISettings: openai_cfg,
            KafkaSettings: kafka_cfg,
            Redis: redis_client,
            KafkaBroker: broker,
        },
    )

    # NACK_ON_ERROR: commit after success; on handler exception seek back for
    # redelivery. Bounded by the consumer's failure counter -> DLQ at max_retries.
    @broker.subscriber(
        kafka_cfg.kafka_topic_insights,
        group_id=_CONSUMER_GROUP,
        ack_policy=AckPolicy.NACK_ON_ERROR,
    )
    async def on_insight_event(
        body: dict[str, Any],
        store: FromDishka[ConsumerIdempotencyStore],
        dlq_publisher: FromDishka[EventPublisher],
        process_insight: FromDishka[ProcessInsightUseCase],
        metrics: FromDishka[MetricsRecorder],
        headers: dict[str, Any] = Context("message.headers"),  # noqa: B008
    ) -> None:
        # Resume the producer's trace (carried over the outbox -> Kafka hop) so
        # consumer-side work shares one trace api -> outbox -> kafka -> worker.
        parent = extract_context(headers)
        with tracer.start_as_current_span(
            "insight.consume", context=parent, kind=trace.SpanKind.CONSUMER
        ):
            await handle_insight_event(
                body,
                store=store,
                dlq_publisher=dlq_publisher,
                process_insight=process_insight,
                metrics=metrics,
                dlq_topic=kafka_cfg.kafka_topic_dlq,
                max_retries=kafka_cfg.consumer_max_retries,
                idempotency_ttl=kafka_cfg.consumer_idempotency_ttl_seconds,
            )

    app = FastStream(broker)
    setup_dishka(container, app, auto_inject=True)

    background_tasks: set[asyncio.Task[None]] = set()

    @app.on_startup
    async def _start_refresh_loop() -> None:
        if obs_cfg.otel_enabled:
            engine = await container.get(AsyncEngine)
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        sf = await container.get(async_sessionmaker[AsyncSession])
        emb = await container.get(TextEmbedder)
        det = await container.get(BehavioralShiftDetector)
        task = asyncio.create_task(
            _embedding_refresh_loop(sf, emb, det), name="embedding-refresh-loop"
        )
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    @app.on_shutdown
    async def _stop_background_tasks() -> None:
        for task in list(background_tasks):
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)

    return app


def main() -> None:
    app = make_app()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
