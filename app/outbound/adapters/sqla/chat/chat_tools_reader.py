import calendar
from datetime import date
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.chat.ports.chat_tools import (
    CategoryAmount,
    CategoryInfo,
    CategoryTrendPoint,
    CategoryTrendResult,
    CurrencyMonthSummary,
    ListCategoriesResult,
    MonthSummaryResult,
    SearchTransactionsResult,
    SpendWindowResult,
    TransactionMatch,
    UserProfileResult,
)
from app.application.common.exceptions import StorageError
from app.application.common.ports.clock import Clock
from app.application.insights.ports.budget_summary_reader import BudgetTransactionRow
from app.domain.services.monthly_aggregator import (
    TransactionRow,
    aggregate,
)
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.category import categories
from app.outbound.persistence_sqla.mappings.transaction import transactions

# Number of months to cover for get_user_profile
_PROFILE_MONTHS = 4


def _to_transaction_rows(rows: list[BudgetTransactionRow]) -> list[TransactionRow]:
    return [
        TransactionRow(
            amount=r.amount,
            currency=r.currency,
            type_=r.type_,
            category_label=r.category_label,
            day_of_month=r.day_of_month,
        )
        for r in rows
    ]


def _build_currency_summaries(
    year: int, month: int, rows: list[BudgetTransactionRow]
) -> list[CurrencyMonthSummary]:
    aggs = aggregate(year, month, _to_transaction_rows(rows))
    result = []
    for agg in aggs:
        top_cats = [
            CategoryAmount(
                category=cat,
                amount=amt,
                currency=agg.currency,
                pct_of_expenses=pct,
            )
            for cat, amt, pct in agg.top_categories
        ]
        result.append(
            CurrencyMonthSummary(
                currency=agg.currency,
                total_income=agg.total_income,
                total_expenses=agg.total_expenses,
                net_savings=agg.net_savings,
                savings_rate=agg.savings_rate,
                top_categories=top_cats,
                transaction_count=agg.transaction_count,
            )
        )
    return result


class SqlaChatToolsReader:
    """Read-only ChatTools impl that opens a FRESH SHORT session per tool call.

    Each public method opens ``async with self._session_factory() as session``,
    runs its (read-only) query, and lets the session close before returning. No
    pooled connection is held across the OpenAI tool-selection round-trips that
    sit between these calls — this preserves the ARCHITECTURE §10.4 / bug B14
    invariant ("no DB connection held across OpenAI calls") for the tools-mode
    chat path. (See ``SqlaChatWorkUnitFactory`` for the RAG-path equivalent.)
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    # ------------------------------------------------------------------
    # get_month_summary
    # ------------------------------------------------------------------

    async def get_month_summary(
        self,
        user_id: str,
        year: int,
        month: int,
    ) -> MonthSummaryResult:
        uid = UserId(value=UUID(user_id))
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        async with self._session_factory() as session:
            rows = await self._fetch_budget_rows(session, uid, first_day, last_day)
        by_currency = _build_currency_summaries(year, month, rows)
        return MonthSummaryResult(year=year, month=month, by_currency=by_currency)

    # ------------------------------------------------------------------
    # get_category_trend
    # ------------------------------------------------------------------

    async def get_category_trend(
        self,
        user_id: str,
        category: str,
        n_months: int,
    ) -> CategoryTrendResult:
        uid = UserId(value=UUID(user_id))
        today = self._clock.now().date()
        before_year, before_month = today.year, today.month

        months: list[tuple[int, int]] = []
        y, m = before_year, before_month
        for _ in range(n_months):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
            months.append((y, m))

        if not months:
            return CategoryTrendResult(category=category, series=[])

        earliest_year, earliest_month = months[-1]
        latest_year, latest_month = months[0]
        first_day = date(earliest_year, earliest_month, 1)
        last_day = date(
            latest_year, latest_month, calendar.monthrange(latest_year, latest_month)[1]
        )

        async with self._session_factory() as session:
            series = await self._fetch_category_trend_series(
                session, uid, category, first_day, last_day
            )
        return CategoryTrendResult(category=category, series=series)

    async def _fetch_category_trend_series(
        self,
        session: AsyncSession,
        user_id: UserId,
        category: str,
        first_day: date,
        last_day: date,
    ) -> list[CategoryTrendPoint]:
        try:
            stmt = (
                sa.select(
                    sa.extract("year", transactions.c.date).label("yr"),
                    sa.extract("month", transactions.c.date).label("mo"),
                    transactions.c.currency_code,
                    sa.func.sum(transactions.c.amount_value).label("total"),
                )
                .outerjoin(categories, transactions.c.category_id == categories.c.id)
                .where(transactions.c.user_id == user_id)
                .where(transactions.c.type == TransactionType.EXPENSE)
                .where(categories.c.name == category)
                .where(transactions.c.date >= first_day)
                .where(transactions.c.date <= last_day)
                .group_by(
                    sa.extract("year", transactions.c.date),
                    sa.extract("month", transactions.c.date),
                    transactions.c.currency_code,
                )
                .order_by(
                    sa.extract("year", transactions.c.date),
                    sa.extract("month", transactions.c.date),
                )
            )
            result = (await session.execute(stmt)).fetchall()
        except SQLAlchemyError as exc:
            raise StorageError from exc

        return [
            CategoryTrendPoint(
                year=int(row.yr),
                month=int(row.mo),
                currency=row.currency_code,
                amount=Decimal(str(row.total)),
            )
            for row in result
        ]

    # ------------------------------------------------------------------
    # get_spend_window
    # ------------------------------------------------------------------

    async def get_spend_window(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> SpendWindowResult:
        uid = UserId(value=UUID(user_id))
        async with self._session_factory() as session:
            rows = await self._fetch_budget_rows(session, uid, start_date, end_date)
        by_currency = _build_currency_summaries(0, 0, rows)
        return SpendWindowResult(
            start_date=start_date,
            end_date=end_date,
            by_currency=by_currency,
        )

    # ------------------------------------------------------------------
    # get_user_profile
    # ------------------------------------------------------------------

    async def get_user_profile(self, user_id: str) -> UserProfileResult:
        uid = UserId(value=UUID(user_id))
        today = self._clock.now().date()
        before_year, before_month = today.year, today.month

        months: list[tuple[int, int]] = []
        y, m = before_year, before_month
        for _ in range(_PROFILE_MONTHS):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
            months.append((y, m))

        if not months:
            return UserProfileResult(months_covered=0, by_currency=[])

        earliest_year, earliest_month = months[-1]
        latest_year, latest_month = months[0]
        first_day = date(earliest_year, earliest_month, 1)
        last_day = date(
            latest_year, latest_month, calendar.monthrange(latest_year, latest_month)[1]
        )
        async with self._session_factory() as session:
            rows = await self._fetch_budget_rows(session, uid, first_day, last_day)
        combined_aggs = _build_currency_summaries(0, 0, rows)
        return UserProfileResult(
            months_covered=len(months),
            by_currency=combined_aggs,
        )

    # ------------------------------------------------------------------
    # search_transactions
    # ------------------------------------------------------------------

    async def search_transactions(
        self,
        user_id: str,
        text: str,
        limit: int,
    ) -> SearchTransactionsResult:
        uid = UserId(value=UUID(user_id))
        pattern = f"%{text}%"
        try:
            stmt = (
                sa.select(
                    transactions.c.id,
                    transactions.c.date,
                    transactions.c.amount_value,
                    transactions.c.currency_code,
                    transactions.c.type,
                    transactions.c.merchant,
                    transactions.c.notes,
                    categories.c.name.label("category_label"),
                )
                .outerjoin(categories, transactions.c.category_id == categories.c.id)
                .where(transactions.c.user_id == uid)
                .where(
                    sa.or_(
                        transactions.c.merchant.ilike(pattern),
                        transactions.c.notes.ilike(pattern),
                    )
                )
                .order_by(transactions.c.date.desc(), transactions.c.created_at.desc())
                .limit(limit)
            )
            async with self._session_factory() as session:
                result = (await session.execute(stmt)).fetchall()
        except SQLAlchemyError as exc:
            raise StorageError from exc

        matches = [
            TransactionMatch(
                transaction_id=str(row.id),
                date=row.date,
                amount=row.amount_value,
                currency=row.currency_code,
                type_=row.type.value if hasattr(row.type, "value") else str(row.type),
                merchant=row.merchant,
                notes=row.notes,
                category=row.category_label,
            )
            for row in result
        ]
        return SearchTransactionsResult(query=text, matches=matches)

    # ------------------------------------------------------------------
    # list_categories
    # ------------------------------------------------------------------

    async def list_categories(self, user_id: str) -> ListCategoriesResult:
        uid = UserId(value=UUID(user_id))
        try:
            stmt = (
                sa.select(
                    categories.c.name,
                    categories.c.type,
                    sa.func.count().label("transaction_count"),
                )
                .join(categories, transactions.c.category_id == categories.c.id)
                .where(transactions.c.user_id == uid)
                .group_by(categories.c.name, categories.c.type)
                .order_by(sa.desc("transaction_count"))
            )
            async with self._session_factory() as session:
                rows = (await session.execute(stmt)).fetchall()
        except SQLAlchemyError as exc:
            raise StorageError from exc

        return ListCategoriesResult(
            categories=[
                CategoryInfo(
                    name=row.name,
                    category_type=row.type.value if hasattr(row.type, "value") else str(row.type),
                    transaction_count=row.transaction_count,
                )
                for row in rows
            ]
        )

    # ------------------------------------------------------------------
    # Shared helper
    # ------------------------------------------------------------------

    async def _fetch_budget_rows(
        self,
        session: AsyncSession,
        user_id: UserId,
        first_day: date,
        last_day: date,
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
            rows = (await session.execute(stmt)).fetchall()
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
