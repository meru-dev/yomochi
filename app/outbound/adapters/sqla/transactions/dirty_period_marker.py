from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.dirty_period import dirty_periods


class SqlaDirtyPeriodMarker:
    """Writes `(user_id, year, month)` rows to `dirty_periods` from the
    transactions BC. Owns the SQL — does not depend on the insights adapter."""

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
