import logging
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.common.ports.event_publisher import EventPublisher
from app.domain.value_objects.enums import OutboxStatus
from app.outbound.observability.prometheus import (
    outbox_pending_total,
    outbox_relay_total,
)
from app.outbound.persistence_sqla.mappings.outbox_event import outbox_events

logger = logging.getLogger(__name__)

_TOPIC_MAP_TYPE = dict[str, str]


class OutboxPoller:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: EventPublisher,
        topic_map: _TOPIC_MAP_TYPE,
        batch_size: int = 100,
        max_retries: int = 5,
    ) -> None:
        self._factory = session_factory
        self._publisher = publisher
        self._topic_map = topic_map
        self._batch_size = batch_size
        self._max_retries = max_retries

    async def run_once(self) -> int:
        """Poll one batch, returning the number of successfully sent rows.

        Each row is handled in its own transaction. A publish failure on row N
        does not roll back rows < N. A row that fails repeatedly is quarantined
        as FAILED after `max_retries` attempts so the queue can drain.
        """
        sent = 0
        # 1. Snapshot the pending IDs to process. We deliberately release the FOR UPDATE
        #    lock from the snapshot query immediately (commit), then re-lock each row
        #    individually inside its own TX. This keeps the per-row TX windows short
        #    and avoids long-held locks across the OpenAI-bound publish call (well,
        #    Kafka-bound, but same shape: network IO inside the TX is bad).
        ids = await self._snapshot_pending_ids()
        if not ids:
            await self._update_pending_gauge()
            return 0

        for row_id in ids:
            ok = await self._process_one(row_id)
            if ok:
                sent += 1

        await self._update_pending_gauge()
        return sent

    async def _snapshot_pending_ids(self) -> list[Any]:
        async with self._factory() as session:
            result = await session.execute(
                sa.select(outbox_events.c.id)
                .where(outbox_events.c.status == OutboxStatus.PENDING)
                .order_by(outbox_events.c.created_at)
                .limit(self._batch_size)
            )
            return [r[0] for r in result.all()]

    async def _process_one(self, row_id: Any) -> bool:
        """Per-row TX. Returns True on successful publish + UPDATE."""
        # Re-acquire the row with SKIP LOCKED so concurrent pollers / restarts don't
        # step on each other. If another worker grabbed it in the gap between snapshot
        # and now, we just skip — no error.
        try:
            async with self._factory.begin() as session:
                row = await self._lock_row(session, row_id)
                if row is None:
                    return False  # taken by another worker, or no longer PENDING
                topic = self._topic_map.get(row["event_type"])
                if topic is None:
                    logger.warning(
                        "no_topic_for_event_type", extra={"event_type": row["event_type"]}
                    )
                    # Quarantine: a row with no topic mapping will never succeed.
                    await self._mark_failed(
                        session, row_id, error=f"no topic for {row['event_type']}"
                    )
                    return False

                message = _build_message(row)
                key = row["user_id"].bytes if row["user_id"] else None
                await self._publisher.publish(message, topic, key=key)

                await session.execute(
                    sa.update(outbox_events)
                    .where(outbox_events.c.id == row_id)
                    .values(status=OutboxStatus.SENT)
                )
                outbox_relay_total.labels(status="sent").inc()
                return True
        except Exception as exc:
            logger.exception("outbox_row_failed", extra={"row_id": str(row_id)})
            outbox_relay_total.labels(status="failed").inc()
            # The publish/update TX rolled back; open a separate TX to record the failure.
            await self._record_failure(row_id, str(exc))
            return False

    async def _lock_row(self, session: AsyncSession, row_id: Any) -> Any:
        result = await session.execute(
            sa.select(outbox_events)
            .where(outbox_events.c.id == row_id)
            .where(outbox_events.c.status == OutboxStatus.PENDING)
            .with_for_update(skip_locked=True)
        )
        return result.mappings().first()

    async def _record_failure(self, row_id: Any, error: str) -> None:
        try:
            async with self._factory.begin() as session:
                current = await session.execute(
                    sa.select(outbox_events.c.retry_count)
                    .where(outbox_events.c.id == row_id)
                    .with_for_update()
                )
                row = current.first()
                if row is None:
                    return
                new_count = (row[0] or 0) + 1
                if new_count >= self._max_retries:
                    await self._mark_failed(session, row_id, error=error, count=new_count)
                else:
                    await session.execute(
                        sa.update(outbox_events)
                        .where(outbox_events.c.id == row_id)
                        .values(retry_count=new_count, last_error=error[:1000])
                    )
        except Exception:
            logger.exception("outbox_record_failure_error", extra={"row_id": str(row_id)})

    async def _mark_failed(
        self, session: AsyncSession, row_id: Any, *, error: str, count: int | None = None
    ) -> None:
        values: dict[str, Any] = {
            "status": OutboxStatus.FAILED,
            "last_error": error[:1000],
            "failed_at": datetime.now(UTC),
        }
        if count is not None:
            values["retry_count"] = count
        await session.execute(
            sa.update(outbox_events).where(outbox_events.c.id == row_id).values(**values)
        )
        outbox_relay_total.labels(status="quarantined").inc()

    async def _update_pending_gauge(self) -> None:
        try:
            async with self._factory() as session:
                result = await session.execute(
                    sa.select(sa.func.count())
                    .select_from(outbox_events)
                    .where(outbox_events.c.status == OutboxStatus.PENDING)
                )
                count = result.scalar_one()
                outbox_pending_total.set(count)
        except Exception:
            logger.exception("outbox_gauge_update_failed")


def _build_message(row: Any) -> dict[str, Any]:
    return {
        "event_id": str(row["id"]),
        "event_type": row["event_type"],
        "aggregate_id": row["aggregate_id"],
        "user_id": str(row["user_id"]) if row["user_id"] else None,
        "payload": row["payload"],
        "occurred_at": row["occurred_at"].isoformat(),
    }
