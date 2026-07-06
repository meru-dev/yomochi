from datetime import date

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.transaction import transactions


class SqlaActiveUserReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def recently_active_user_ids(self, since: date) -> list[UserId]:
        try:
            stmt = sa.select(transactions.c.user_id).where(transactions.c.date >= since).distinct()
            rows = (await self._session.execute(stmt)).fetchall()
        except SQLAlchemyError as exc:
            raise StorageError from exc
        # transactions.c.user_id is UserIdType, so result values are already UserId.
        return [r.user_id for r in rows]
