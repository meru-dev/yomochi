import calendar
from datetime import date

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.insights.ports.budget_summary_reader import (
    BudgetTransactionRow,
)
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.category import categories
from app.outbound.persistence_sqla.mappings.transaction import transactions


class SqlaBudgetSummaryReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_month(
        self, user_id: UserId, year: int, month: int
    ) -> list[BudgetTransactionRow]:
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        return await self._fetch(user_id, first_day, last_day)

    async def read_history_months(
        self,
        user_id: UserId,
        before_year: int,
        before_month: int,
        n_months: int,
    ) -> dict[tuple[int, int], list[BudgetTransactionRow]]:
        if n_months == 0:
            return {}

        # Build the list of (year, month) keys we want, walking backwards.
        months: list[tuple[int, int]] = []
        year, month = before_year, before_month
        for _ in range(n_months):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
            months.append((year, month))

        earliest_year, earliest_month = months[-1]
        latest_year, latest_month = months[0]

        first_day = date(earliest_year, earliest_month, 1)
        last_day = date(
            latest_year, latest_month, calendar.monthrange(latest_year, latest_month)[1]
        )

        try:
            stmt = (
                sa.select(
                    transactions.c.amount_value,
                    transactions.c.currency_code,
                    transactions.c.type,
                    transactions.c.date,
                    categories.c.name.label("category_label"),
                )
                .outerjoin(categories, transactions.c.category_id == categories.c.id)
                .where(transactions.c.user_id == user_id)
                .where(transactions.c.date >= first_day)
                .where(transactions.c.date <= last_day)
            )
            raw_rows = (await self._session.execute(stmt)).fetchall()
        except SQLAlchemyError as exc:
            raise StorageError from exc

        result: dict[tuple[int, int], list[BudgetTransactionRow]] = {m: [] for m in months}
        for r in raw_rows:
            key = (r.date.year, r.date.month)
            if key in result:
                result[key].append(
                    BudgetTransactionRow(
                        amount=r.amount_value,
                        currency=r.currency_code,
                        type_=r.type.value if hasattr(r.type, "value") else str(r.type),
                        category_label=r.category_label,
                        day_of_month=r.date.day,
                    )
                )
        return result

    async def _fetch(
        self, user_id: UserId, first_day: date, last_day: date
    ) -> list[BudgetTransactionRow]:
        try:
            stmt = (
                sa.select(
                    transactions.c.amount_value,
                    transactions.c.currency_code,
                    transactions.c.type,
                    transactions.c.date,
                    categories.c.name.label("category_label"),
                )
                .outerjoin(categories, transactions.c.category_id == categories.c.id)
                .where(transactions.c.user_id == user_id)
                .where(transactions.c.date >= first_day)
                .where(transactions.c.date <= last_day)
            )
            rows = (await self._session.execute(stmt)).fetchall()
            return [
                BudgetTransactionRow(
                    amount=r.amount_value,
                    currency=r.currency_code,
                    type_=r.type.value if hasattr(r.type, "value") else str(r.type),
                    category_label=r.category_label,
                    day_of_month=r.date.day,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            raise StorageError from exc
