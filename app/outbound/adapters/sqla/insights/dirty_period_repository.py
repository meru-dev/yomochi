from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.insights.ports.dirty_period_repository import DirtyPeriod
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.dirty_period import dirty_periods


class SqlaDirtyPeriodRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def mark_dirty(self, user_id: UserId, year: int, month: int) -> None:
        try:
            stmt = (
                pg_insert(dirty_periods)
                .values(
                    user_id=user_id.value,
                    year=year,
                    month=month,
                    created_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing(index_elements=["user_id", "year", "month"])
            )
            await self._session.execute(stmt)
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def pop_dirty(self, limit: int = 100) -> list[DirtyPeriod]:
        try:
            select_stmt = (
                sa.select(dirty_periods)
                .order_by(dirty_periods.c.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = (await self._session.execute(select_stmt)).fetchall()
            if not rows:
                return []
            ids = [r.id for r in rows]
            await self._session.execute(sa.delete(dirty_periods).where(dirty_periods.c.id.in_(ids)))
            return [
                DirtyPeriod(user_id=UserId(r.user_id), year=r.year, month=r.month) for r in rows
            ]
        except SQLAlchemyError as exc:
            raise StorageError from exc
