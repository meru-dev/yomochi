from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.application.transactions.ports.budget_summary_reader import (
    BudgetSummaryReader,
    CurrencyTotalRow,
)
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.reporting_period import MonthPeriod


@dataclass(frozen=True, slots=True)
class GetBudgetSummaryCommand:
    user_id: UserId
    year: int
    month: int


@dataclass(frozen=True, slots=True)
class CurrencyTotal:
    currency: str
    total: Decimal
    count: int


@dataclass(frozen=True, slots=True)
class BudgetSummaryResult:
    expenses: list[CurrencyTotal]
    income: list[CurrencyTotal]


class GetBudgetSummaryUseCase:
    def __init__(self, reader: BudgetSummaryReader) -> None:
        self._reader = reader

    async def __call__(self, command: GetBudgetSummaryCommand) -> BudgetSummaryResult:
        period = MonthPeriod(year=command.year, month=command.month)
        today = datetime.now(UTC).date()
        _, clipped_end = period.bounds_clipped_to(today)
        rows = await self._reader.read_clipped(command.user_id, period, clipped_end)
        return _split_by_type(rows)


def _split_by_type(rows: list[CurrencyTotalRow]) -> BudgetSummaryResult:
    expenses: list[CurrencyTotal] = []
    income: list[CurrencyTotal] = []
    for row in rows:
        bucket = CurrencyTotal(currency=row.currency, total=row.total, count=row.count)
        if row.type_ == TransactionType.EXPENSE:
            expenses.append(bucket)
        else:
            income.append(bucket)
    return BudgetSummaryResult(expenses=expenses, income=income)
