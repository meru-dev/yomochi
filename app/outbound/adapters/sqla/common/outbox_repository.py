from uuid import UUID

import sqlalchemy as sa
import uuid_utils
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.common.outbox_event import OutboxEvent
from app.application.common.ports.outbox_repository import OutboxRepository
from app.domain.value_objects.enums import OutboxStatus
from app.outbound.observability.propagation import PROPAGATOR
from app.outbound.persistence_sqla.mappings.outbox_event import outbox_events


def _new_outbox_id() -> UUID:
    return UUID(str(uuid_utils.uuid7()))


def _capture_trace_context() -> dict[str, str] | None:
    """W3C carrier for the active span, or None when no span is recording.

    Persisted into outbox_events.trace_context so the outbox-worker can resume
    the producer's trace when it relays the row to Kafka.
    """
    carrier: dict[str, str] = {}
    PROPAGATOR.inject(carrier)
    return carrier or None


class SqlaOutboxRepository(OutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: OutboxEvent) -> None:
        try:
            await self._session.execute(
                sa.insert(outbox_events).values(
                    id=_new_outbox_id(),
                    event_type=event.event_type,
                    aggregate_id=event.aggregate_id,
                    payload=event.payload,
                    status=OutboxStatus.PENDING,
                    occurred_at=event.occurred_at,
                    user_id=event.user_id,
                    trace_context=_capture_trace_context(),
                )
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc
