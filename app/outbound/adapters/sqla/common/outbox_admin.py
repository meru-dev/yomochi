from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.common.ports.outbox_admin import OutboxAdmin
from app.domain.value_objects.enums import OutboxStatus
from app.outbound.persistence_sqla.mappings.outbox_event import outbox_events


class SqlaOutboxAdmin(OutboxAdmin):
    """Operational outbox maintenance (F17). Separate from the request-path
    ``SqlaOutboxRepository`` so the hot write path stays append-only."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def requeue_failed(
        self,
        *,
        ids: Sequence[UUID] | None = None,
        event_type: str | None = None,
        failed_before: datetime | None = None,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> list[UUID]:
        conds = [outbox_events.c.status == OutboxStatus.FAILED]
        if ids is not None:
            conds.append(outbox_events.c.id.in_(list(ids)))
        if event_type is not None:
            conds.append(outbox_events.c.event_type == event_type)
        if failed_before is not None:
            conds.append(outbox_events.c.failed_at < failed_before)

        try:
            # Select the target ids first (oldest-failure-first, capped by limit).
            # SKIP LOCKED so a running poller / concurrent replay can't fight over
            # the same rows.
            select_ids = (
                sa.select(outbox_events.c.id)
                .where(*conds)
                .order_by(outbox_events.c.failed_at.asc().nulls_last())
                .with_for_update(skip_locked=True)
            )
            if limit is not None:
                select_ids = select_ids.limit(limit)

            result = await self._session.execute(select_ids)
            target_ids = [r[0] for r in result.all()]
            if dry_run or not target_ids:
                return target_ids

            await self._session.execute(
                sa.update(outbox_events)
                .where(outbox_events.c.id.in_(target_ids))
                .values(
                    status=OutboxStatus.PENDING,
                    retry_count=0,
                    last_error=None,
                    failed_at=None,
                )
            )
            return target_ids
        except SQLAlchemyError as exc:
            raise StorageError from exc
