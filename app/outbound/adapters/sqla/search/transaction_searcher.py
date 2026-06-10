from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.transaction import transactions


def _escape_like(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlaTransactionSearcher:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, user_id: UserId, query: str, limit: int = 20) -> list[Transaction]:
        q = f"%{_escape_like(query)}%"
        stmt = (
            select(Transaction)
            .where(transactions.c.user_id == user_id)
            .where(
                or_(
                    transactions.c.merchant.ilike(q, escape="\\"),
                    transactions.c.notes.ilike(q, escape="\\"),
                )
            )
            .order_by(transactions.c.date.desc(), transactions.c.created_at.desc())
            .limit(limit)
        )
        try:
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            raise StorageError from exc
