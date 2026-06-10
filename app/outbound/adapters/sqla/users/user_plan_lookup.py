from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.value_objects.enums import Plan
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.user import users


class SqlaUserPlanLookup:
    """Lightweight read-only plan resolver — single column, no entity hydration."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_plan(self, user_id: UserId) -> Plan:
        try:
            row = (
                await self._session.execute(select(users.c.plan).where(users.c.id == user_id))
            ).first()
        except SQLAlchemyError as exc:
            raise StorageError from exc
        if row is None:
            return Plan.FREE
        return Plan(row.plan)
