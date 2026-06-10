from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.common.ports.quota_check import QuotaExceededError, QuotaResource
from app.domain.value_objects.enums import Plan
from app.domain.value_objects.ids import UserId
from app.outbound.observability.prometheus import quota_blocked_total
from app.outbound.persistence_sqla.mappings.insight import insights
from app.outbound.persistence_sqla.mappings.transaction import transactions

_PLAN_LIMITS: dict[Plan, dict[QuotaResource, int]] = {
    Plan.FREE: {
        QuotaResource.TRANSACTIONS: 500,
        QuotaResource.INSIGHTS: 30,
    },
    Plan.DEMO: {
        QuotaResource.TRANSACTIONS: 5_000,
        QuotaResource.INSIGHTS: 300,
    },
}


def _current_year_month() -> tuple[int, int]:
    now = datetime.now(UTC)
    return now.year, now.month


class SqlaQuotaCheck:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_and_increment(
        self, user_id: UserId, resource: QuotaResource, plan: Plan
    ) -> None:
        # "Increment" is the caller's INSERT in the same TX — no separate counter.
        # count() here reads committed rows; if count >= limit, the new insert
        # would exceed the quota. ADR-0023.
        limit = _PLAN_LIMITS.get(plan, {}).get(resource, 0)
        year, month = _current_year_month()
        count = await self._count(user_id, resource, year, month)
        if count >= limit:
            quota_blocked_total.labels(resource=resource.value, plan=plan.value).inc()
            raise QuotaExceededError(resource=resource, current=count + 1, limit=limit)

    async def _count(self, user_id: UserId, resource: QuotaResource, year: int, month: int) -> int:
        table = transactions if resource == QuotaResource.TRANSACTIONS else insights
        try:
            result = await self._session.execute(
                sa.select(sa.func.count()).where(
                    table.c.user_id == user_id,
                    sa.extract("year", table.c.created_at) == year,
                    sa.extract("month", table.c.created_at) == month,
                )
            )
            return result.scalar_one()
        except SQLAlchemyError as exc:
            raise StorageError from exc
