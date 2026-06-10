from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.transactions.ports.budget_summary_reader import (
    BudgetSummaryReader,
    CurrencyTotalRow,
)
from app.application.transactions.use_cases.get_budget_summary import (
    GetBudgetSummaryCommand,
    GetBudgetSummaryUseCase,
)
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.reporting_period import MonthPeriod


class _FakeReader:
    def __init__(self, rows: list[CurrencyTotalRow]) -> None:
        self.rows = rows
        self.captured: dict[str, object] = {}

    async def read_clipped(
        self, user_id: UserId, period: MonthPeriod, clipped_to: date
    ) -> list[CurrencyTotalRow]:
        self.captured["user_id"] = user_id
        self.captured["period"] = period
        self.captured["clipped_to"] = clipped_to
        return self.rows


@pytest.mark.asyncio
async def test_splits_rows_by_type() -> None:
    user_id = UserId(uuid4())
    reader: BudgetSummaryReader = _FakeReader(
        [
            CurrencyTotalRow("USD", TransactionType.EXPENSE, Decimal("125.50"), 3),
            CurrencyTotalRow("USD", TransactionType.INCOME, Decimal("5000.00"), 1),
            CurrencyTotalRow("JPY", TransactionType.EXPENSE, Decimal("8000"), 5),
        ]
    )
    use_case = GetBudgetSummaryUseCase(reader=reader)

    result = await use_case(GetBudgetSummaryCommand(user_id=user_id, year=2026, month=2))

    assert len(result.expenses) == 2
    assert len(result.income) == 1
    assert result.income[0].currency == "USD"
    assert result.income[0].total == Decimal("5000.00")


@pytest.mark.asyncio
async def test_passes_validated_period_to_reader() -> None:
    user_id = UserId(uuid4())
    fake = _FakeReader([])
    use_case = GetBudgetSummaryUseCase(reader=fake)

    await use_case(GetBudgetSummaryCommand(user_id=user_id, year=2026, month=3))

    assert fake.captured["period"] == MonthPeriod(year=2026, month=3)
    assert fake.captured["user_id"] == user_id


@pytest.mark.asyncio
async def test_rejects_bad_month() -> None:
    user_id = UserId(uuid4())
    use_case = GetBudgetSummaryUseCase(reader=_FakeReader([]))

    with pytest.raises(ValueError):
        await use_case(GetBudgetSummaryCommand(user_id=user_id, year=2026, month=13))
