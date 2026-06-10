from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.entities.recurring_rule import RecurringRule
from app.domain.value_objects.ids import RecurringRuleId, UserId
from app.outbound.persistence_sqla.mappings.recurring_rule import recurring_rules


class SqlaRecurringRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, rule: RecurringRule) -> None:
        try:
            await self._session.merge(rule)
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get(self, id_: RecurringRuleId, user_id: UserId) -> RecurringRule | None:
        try:
            result = await self._session.execute(
                select(RecurringRule)
                .where(recurring_rules.c.id == id_)
                .where(recurring_rules.c.user_id == user_id)
            )
            return result.scalars().first()
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def list_(self, user_id: UserId) -> list[RecurringRule]:
        try:
            result = await self._session.execute(
                select(RecurringRule)
                .where(recurring_rules.c.user_id == user_id)
                .order_by(recurring_rules.c.created_at.desc())
            )
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def delete(self, id_: RecurringRuleId, user_id: UserId) -> None:
        try:
            await self._session.execute(
                delete(RecurringRule)
                .where(recurring_rules.c.id == id_)
                .where(recurring_rules.c.user_id == user_id)
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def fetch_due_for_update(self, as_of: date, limit: int) -> list[RecurringRule]:
        try:
            result = await self._session.execute(
                select(RecurringRule)
                .where(recurring_rules.c.next_fire_date <= as_of)
                .where(recurring_rules.c.status == "active")
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            raise StorageError from exc
