import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.transaction import transactions


class SqlaTransactionReader:
    """Consumer-owned read port for the insights context.

    Reads directly from transactions_table per CODING_STANDARDS §3.4 Pattern 1.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_for_period(self, user_id: UserId, year: int, month: int) -> int:
        try:
            result = await self._session.execute(
                sa.select(sa.func.count()).where(
                    transactions.c.user_id == user_id,
                    sa.extract("year", transactions.c.date) == year,
                    sa.extract("month", transactions.c.date) == month,
                )
            )
            return result.scalar_one()
        except SQLAlchemyError as exc:
            raise StorageError from exc
