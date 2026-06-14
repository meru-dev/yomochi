from typing import Any

import structlog

from app.application.common.ports.consumer_idempotency_store import ConsumerIdempotencyStore
from app.application.common.ports.event_publisher import EventPublisher
from app.application.common.ports.metrics_recorder import MetricsRecorder
from app.application.insights.ports.insight_repository import (
    InsightAlreadyTerminalError,
    InsightNotFoundError,
)
from app.application.insights.use_cases.process_insight import (
    ProcessInsightCommand,
    ProcessInsightUseCase,
)
from app.inbound.messaging._event_id import resolve_event_id

logger = structlog.get_logger(__name__)

_TOPIC = "yomochi.insights.v1"


async def handle_insight_event(
    body: dict[str, Any],
    *,
    store: ConsumerIdempotencyStore,
    dlq_publisher: EventPublisher,
    process_insight: ProcessInsightUseCase,
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
        if event_type == "InsightRequested":
            insight_id: str = body.get("payload", {}).get("insight_id", "")
            user_id: str = body.get("payload", {}).get("user_id", "")
            if not insight_id or not user_id:
                raise ValueError(
                    f"insight_event_malformed_payload: insight_id={insight_id!r} user_id={user_id!r}"
                )
            try:
                result = await process_insight(
                    ProcessInsightCommand(insight_id=insight_id, user_id=user_id)
                )
                metrics.insight_generation_observed(
                    result.context_quality.value, result.elapsed_seconds
                )
            except (InsightAlreadyTerminalError, InsightNotFoundError) as terminal:
                # Re-delivery of an event whose insight is already terminal/missing.
                # Treat as success: mark_processed so we don't DLQ a durably-done row.
                logger.info(
                    "insight_event_terminal_skip",
                    event_id=event_id,
                    insight_id=insight_id,
                    reason=type(terminal).__name__,
                )
        else:
            logger.info("insight_event_ignored", event_id=event_id, event_type=event_type)

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
