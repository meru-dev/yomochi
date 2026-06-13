from datetime import date
from typing import Any
from uuid import UUID

import structlog

from app.application.common.ports.consumer_idempotency_store import ConsumerIdempotencyStore
from app.application.common.ports.event_publisher import EventPublisher
from app.application.common.ports.metrics_recorder import MetricsRecorder
from app.application.insights.ports.dirty_period_repository import DirtyPeriodRepository
from app.domain.value_objects.ids import UserId
from app.inbound.messaging._event_id import resolve_event_id

logger = structlog.get_logger(__name__)

_TOPIC = "yomochi.transactions.v1"


async def handle_transaction_event(
    body: dict[str, Any],
    *,
    store: ConsumerIdempotencyStore,
    dlq_publisher: EventPublisher,
    dirty_period_repo: DirtyPeriodRepository,
    metrics: MetricsRecorder,
    dlq_topic: str,
    max_retries: int,
    idempotency_ttl: int,
) -> None:
    event_id: str = resolve_event_id(body)
    if not body.get("event_id"):
        logger.warning(
            "consumer_event_missing_id",
            topic=_TOPIC,
            body_keys=list(body.keys()),
            event_type=body.get("event_type"),
        )
    event_type: str = body.get("event_type", "unknown")

    if await store.is_processed(event_id):
        logger.info("consumer_skipped_duplicate", event_id=event_id, event_type=event_type)
        metrics.consumer_idempotency_skip(_TOPIC)
        return

    try:
        raw_user_id: str | None = body.get("user_id")
        payload: dict[str, Any] = body.get("payload") or {}
        if raw_user_id:
            user_id = UserId(UUID(raw_user_id))
            tx_date_str: str | None = payload.get("transaction_date")
            if tx_date_str:
                tx_date = date.fromisoformat(tx_date_str)
                await dirty_period_repo.mark_dirty(user_id, tx_date.year, tx_date.month)
                old_date_str: str | None = payload.get("old_date")
                if old_date_str:
                    old_date = date.fromisoformat(old_date_str)
                    await dirty_period_repo.mark_dirty(user_id, old_date.year, old_date.month)

        logger.info("transaction_event_handled", event_id=event_id, event_type=event_type)
        await store.mark_processed(event_id, ttl_seconds=idempotency_ttl)

    except Exception as exc:
        failures = await store.increment_failures(event_id)
        logger.warning(
            "consumer_handler_failed",
            event_id=event_id,
            attempt=failures,
            error=str(exc),
            exc_info=True,
        )
        if failures >= max_retries:
            await dlq_publisher.publish(
                message={**body, "x_error": str(exc)},
                topic=dlq_topic,
            )
            await store.mark_processed(event_id, ttl_seconds=idempotency_ttl)
            metrics.consumer_dlq_event(_TOPIC)
            logger.error("consumer_event_parked_in_dlq", event_id=event_id)
        else:
            raise
