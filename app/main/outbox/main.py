import asyncio

import structlog
from faststream.kafka import KafkaBroker
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.common.ports.event_publisher import EventPublisher
from app.main.config.loader import (
    load_database_settings,
    load_kafka_settings,
    load_observability_settings,
)
from app.main.config.settings import (
    DatabaseSettings,
    KafkaSettings,
    ObservabilitySettings,
)
from app.main.logging import configure_logging
from app.outbound.adapters.kafka.event_publisher import KafkaEventPublisher
from app.outbound.outbox.poller import OutboxPoller
from app.outbound.persistence_sqla.mappings.all import map_tables

logger = structlog.get_logger(__name__)


async def run(
    db_settings: DatabaseSettings,
    kafka_settings: KafkaSettings,
    obs_settings: ObservabilitySettings,
) -> None:
    map_tables()
    configure_logging(log_format=obs_settings.log_format, debug=False)

    engine = create_async_engine(db_settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)

    broker = KafkaBroker(bootstrap_servers=kafka_settings.kafka_bootstrap_servers, acks="all")
    await broker.start()
    publisher: EventPublisher = KafkaEventPublisher(broker=broker)

    topic_map = {
        "TransactionCreated": kafka_settings.kafka_topic_transactions,
        "TransactionUpdated": kafka_settings.kafka_topic_transactions,
        "TransactionDeleted": kafka_settings.kafka_topic_transactions,
        "InsightRequested": kafka_settings.kafka_topic_insights,
        "InsightCompleted": kafka_settings.kafka_topic_insights,
    }
    poller = OutboxPoller(
        session_factory=session_factory,
        publisher=publisher,
        topic_map=topic_map,
        batch_size=kafka_settings.outbox_batch_size,
        max_retries=kafka_settings.outbox_max_retries,
    )

    logger.info("outbox_worker_started")
    try:
        while True:
            try:
                sent = await poller.run_once()
                if sent:
                    logger.info("outbox_batch_sent", count=sent)
            except Exception:
                logger.exception("outbox_poll_error")
            await asyncio.sleep(kafka_settings.outbox_poll_interval_seconds)
    finally:
        await broker.close()
        await engine.dispose()


def main() -> None:
    db_settings = load_database_settings()
    kafka_settings = load_kafka_settings()
    obs_settings = load_observability_settings()
    asyncio.run(run(db_settings, kafka_settings, obs_settings))


if __name__ == "__main__":
    main()
