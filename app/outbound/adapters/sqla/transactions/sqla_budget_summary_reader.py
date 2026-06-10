from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.transactions.ports.budget_summary_reader import (
    BudgetSummaryReader,
    CurrencyTotalRow,
)
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.reporting_period import MonthPeriod
from app.outbound.persistence_sqla.mappings.transaction import transactions


class SqlaBudgetSummaryReader(BudgetSummaryReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_clipped(
        self,
        user_id: UserId,
        period: MonthPeriod,
        clipped_to: date,
    ) -> list[CurrencyTotalRow]:
        start, end = period.bounds_clipped_to(clipped_to)
        result = await self._session.execute(
            select(
                transactions.c.currency_code,
                transactions.c.type,
                func.sum(transactions.c.amount_value).label("total"),
                func.count().label("count"),
            )
            .where(
                transactions.c.user_id == user_id,
                transactions.c.date >= start,
                transactions.c.date <= end,
            )
            .group_by(transactions.c.currency_code, transactions.c.type)
        )
        return [
            CurrencyTotalRow(
                currency=row.currency_code,
                type_=row.type
                if isinstance(row.type, TransactionType)
                else TransactionType(row.type),
                total=Decimal(row.total),
                count=int(row._mapping["count"]),
            )
            for row in result
        ]
