from datetime import timedelta
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.transactions.ports.spend_trend_reader import (
    SpendTrendReader,
    TrendBucket,
)
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.money import Currency
from app.domain.value_objects.reporting_period import TrendWindow
from app.outbound.persistence_sqla.mappings.transaction import transactions


class SqlaSpendTrendReader(SpendTrendReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(
        self,
        user_id: UserId,
        currency: Currency,
        type_: TransactionType,
        window: TrendWindow,
    ) -> list[TrendBucket]:
        if window.granularity == "week":
            bucket_expr = func.to_char(transactions.c.date, sa.literal_column("'IYYY-\"W\"IW'"))
            floor_date = window.end - timedelta(weeks=window.bucket_count - 1)
            # Align floor to start of the ISO week (Monday) of the oldest bucket
            floor_date = floor_date - timedelta(days=floor_date.weekday())
        else:
            bucket_expr = func.to_char(transactions.c.date, sa.literal_column("'YYYY-MM'"))
            year = window.end.year
            month = window.end.month - (window.bucket_count - 1)
            while month <= 0:
                month += 12
                year -= 1
            floor_date = window.end.replace(year=year, month=month, day=1)

        result = await self._session.execute(
            select(
                bucket_expr.label("bucket"),
                func.sum(transactions.c.amount_value).label("total"),
            )
            .where(
                transactions.c.user_id == user_id,
                transactions.c.currency_code == currency.code,
                transactions.c.type == type_,
                transactions.c.date >= floor_date,
                transactions.c.date <= window.end,
            )
            .group_by(bucket_expr)
            .order_by(sa.text("bucket"))
        )
        return [TrendBucket(label=row.bucket, total=Decimal(row.total)) for row in result]
