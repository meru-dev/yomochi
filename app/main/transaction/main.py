import asyncio
from typing import Any

import redis.asyncio as aioredis
import structlog
from dishka import make_async_container
from dishka_faststream import FromDishka, setup_dishka
from faststream import AckPolicy, Context, FastStream
from faststream.kafka import KafkaBroker
from opentelemetry import trace
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.common.ports.consumer_idempotency_store import ConsumerIdempotencyStore
from app.application.common.ports.event_publisher import EventPublisher
from app.application.common.ports.metrics_recorder import MetricsRecorder
from app.application.insights.ports.dirty_period_repository import DirtyPeriodRepository
from app.inbound.messaging.transaction_consumer import handle_transaction_event
from app.main.config.loader import (
    load_database_settings,
    load_kafka_settings,
    load_observability_settings,
    load_redis_settings,
)
from app.main.config.settings import (
    DatabaseSettings,
    KafkaSettings,
    ObservabilitySettings,
    RedisSettings,
)
from app.main.ioc.worker_providers import (
    TransactionPersistenceProvider,
    WorkerAdaptersBaseProvider,
    WorkerInfraProvider,
)
from app.main.logging import configure_logging
from app.outbound.observability.otel import configure_otel
from app.outbound.observability.propagation import extract_context
from app.outbound.persistence_sqla.mappings.all import map_tables

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_CONSUMER_GROUP = "transaction-worker"


def make_app(
    db_settings: DatabaseSettings | None = None,
    redis_settings: RedisSettings | None = None,
    kafka_settings: KafkaSettings | None = None,
    obs_settings: ObservabilitySettings | None = None,
) -> FastStream:
    db_cfg = db_settings or load_database_settings()
    redis_cfg = redis_settings or load_redis_settings()
    kafka_cfg = kafka_settings or load_kafka_settings()
    obs_cfg = obs_settings or load_observability_settings()

    map_tables()
    configure_logging(log_format=obs_cfg.log_format, debug=False)
    configure_otel(
        service_name="yomochi-transaction-worker",
        otlp_endpoint=obs_cfg.otel_exporter_otlp_endpoint,
        enabled=obs_cfg.otel_enabled,
    )

    if obs_cfg.otel_enabled:
        RedisInstrumentor().instrument()

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
        TransactionPersistenceProvider(),
        context={
            DatabaseSettings: db_cfg,
            KafkaSettings: kafka_cfg,
            Redis: redis_client,
            KafkaBroker: broker,
        },
    )

    # NACK_ON_ERROR: commit after success; on handler exception seek back for
    # redelivery. Bounded by the consumer's failure counter -> DLQ at max_retries.
    @broker.subscriber(
        kafka_cfg.kafka_topic_transactions,
        group_id=_CONSUMER_GROUP,
        ack_policy=AckPolicy.NACK_ON_ERROR,
    )
    async def on_transaction_event(
        body: dict[str, Any],
        store: FromDishka[ConsumerIdempotencyStore],
        dlq_publisher: FromDishka[EventPublisher],
        dirty_period_repo: FromDishka[DirtyPeriodRepository],
        metrics: FromDishka[MetricsRecorder],
        headers: dict[str, Any] = Context("message.headers"),  # noqa: B008
    ) -> None:
        # Resume the producer's trace (carried over the outbox -> Kafka hop) so
        # consumer-side work shares one trace api -> outbox -> kafka -> worker.
        parent = extract_context(headers)
        with tracer.start_as_current_span(
            "transaction.consume", context=parent, kind=trace.SpanKind.CONSUMER
        ):
            await handle_transaction_event(
                body,
                store=store,
                dlq_publisher=dlq_publisher,
                dirty_period_repo=dirty_period_repo,
                metrics=metrics,
                dlq_topic=kafka_cfg.kafka_topic_dlq,
                max_retries=kafka_cfg.consumer_max_retries,
                idempotency_ttl=kafka_cfg.consumer_idempotency_ttl_seconds,
            )

    app = FastStream(broker)
    setup_dishka(container, app, auto_inject=True)

    @app.on_startup
    async def _instrument_sqlalchemy() -> None:
        if obs_cfg.otel_enabled:
            engine = await container.get(AsyncEngine)
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    return app


def main() -> None:
    app = make_app()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
