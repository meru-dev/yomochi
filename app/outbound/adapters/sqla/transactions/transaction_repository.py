from datetime import date, datetime
from uuid import UUID

from sqlalchemy import delete, extract, func, select, tuple_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import TransactionId, UserId
from app.outbound.persistence_sqla.mappings.transaction import transactions


class SqlaTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, transaction: Transaction) -> None:
        try:
            await self._session.merge(transaction)
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_by_id(self, transaction_id: TransactionId, user_id: UserId) -> Transaction | None:
        try:
            result = await self._session.execute(
                select(Transaction)
                .where(transactions.c.id == transaction_id)
                .where(transactions.c.user_id == user_id)
            )
            return result.scalars().first()
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def list_by_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[date, datetime, UUID] | None,
        type_filter: str | None = None,
        currency_filter: str | None = None,
        category_id_filter: str | None = None,
    ) -> list[Transaction]:
        try:
            query = (
                select(Transaction)
                .where(transactions.c.user_id == user_id)
                .order_by(
                    transactions.c.date.desc(),
                    transactions.c.created_at.desc(),
                    transactions.c.id.desc(),
                )
                .limit(limit)
            )
            if cursor is not None:
                cursor_date, cursor_created_at, cursor_id = cursor
                query = query.where(
                    tuple_(
                        transactions.c.date,
                        transactions.c.created_at,
                        transactions.c.id,
                    )
                    < (cursor_date, cursor_created_at, cursor_id)
                )
            if type_filter is not None:
                query = query.where(transactions.c.type == type_filter)
            if currency_filter is not None:
                query = query.where(transactions.c.currency_code == currency_filter)
            if category_id_filter is not None:
                query = query.where(transactions.c.category_id == UUID(category_id_filter))
            result = await self._session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_by_ids(self, ids: list[TransactionId], user_id: UserId) -> list[Transaction]:
        if not ids:
            return []
        try:
            id_values = [tid.value for tid in ids]
            result = await self._session.execute(
                select(Transaction)
                .where(transactions.c.user_id == user_id)
                .where(transactions.c.id.in_(id_values))
            )
            by_id = {tx.id_.value: tx for tx in result.scalars().all()}
            return [by_id[tid.value] for tid in ids if tid.value in by_id]
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def count_created_in_month(self, user_id: UserId, year: int, month: int) -> int:
        try:
            result = await self._session.execute(
                select(func.count())
                .where(transactions.c.user_id == user_id)
                .where(extract("year", transactions.c.date) == year)
                .where(extract("month", transactions.c.date) == month)
            )
            return int(result.scalar_one())
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def delete(self, transaction_id: TransactionId, user_id: UserId) -> bool:
        try:
            result = await self._session.execute(
                delete(transactions)
                .where(transactions.c.id == transaction_id)
                .where(transactions.c.user_id == user_id)
            )
            deleted_count: int = result.rowcount  # type: ignore[attr-defined]
            return deleted_count > 0
        except SQLAlchemyError as exc:
            raise StorageError from exc
