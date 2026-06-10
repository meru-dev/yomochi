from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import TransactionId, UserId
from app.outbound.persistence_sqla.mappings.transaction import transactions


class SqlaSearchTransactionReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_ids(self, ids: list[TransactionId], user_id: UserId) -> list[Transaction]:
        if not ids:
            return []
        try:
            result = await self._session.execute(
                select(Transaction)
                .where(transactions.c.user_id == user_id)
                .where(transactions.c.id.in_(ids))
            )
            by_id = {tx.id_.value: tx for tx in result.scalars().all()}
            return [by_id[tid.value] for tid in ids if tid.value in by_id]
        except SQLAlchemyError as exc:
            raise StorageError from exc
