from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.insights.ports.budget_summary_reader import BudgetTransactionRow
from app.application.insights.use_cases.detect_shift_alerts import DetectShiftAlertsUseCase
from app.domain.services.behavioral_shift_detector import DetectedShift
from app.domain.value_objects.ids import UserId


class _FakeBudgetReader:
    """Fake BudgetSummaryReader: serves canned rows for the current month and history."""

    def __init__(
        self,
        current: list[BudgetTransactionRow],
        history: dict[tuple[int, int], list[BudgetTransactionRow]],
    ) -> None:
        self._current = current
        self._history = history
        self.read_month_calls: list[tuple[UserId, int, int]] = []

    async def read_month(
        self, user_id: UserId, year: int, month: int
    ) -> list[BudgetTransactionRow]:
        self.read_month_calls.append((user_id, year, month))
        return self._current

    async def read_history_months(
        self,
        user_id: UserId,
        before_year: int,
        before_month: int,
        n_months: int,
    ) -> dict[tuple[int, int], list[BudgetTransactionRow]]:
        return self._history


class _FakeAlertWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[UserId, int, int, list[DetectedShift]]] = []

    async def write_shift_alerts(
        self,
        user_id: UserId,
        year: int,
        month: int,
        shifts: list[DetectedShift],
    ) -> None:
        self.calls.append((user_id, year, month, shifts))


def _row(
    amount: str,
    type_: str = "expense",
    currency: str = "USD",
    category: str | None = "Food",
    day: int = 5,
) -> BudgetTransactionRow:
    return BudgetTransactionRow(
        amount=Decimal(amount),
        currency=currency,
        type_=type_,
        category_label=category,
        day_of_month=day,
    )


def _month(
    expenses: str, income: str = "1000", currency: str = "USD"
) -> list[BudgetTransactionRow]:
    # At least 2 daily expense buckets so volatility/aggregation behaves like real data.
    return [
        _row(income, type_="income", currency=currency, category="Salary", day=1),
        _row(expenses, type_="expense", currency=currency, category="Food", day=5),
        _row("1", type_="expense", currency=currency, category="Food", day=6),
    ]


@pytest.mark.asyncio
async def test_writes_alerts_when_shift_detected() -> None:
    """Current month with a spike vs >=2 history months -> write_shift_alerts called."""
    uid = UserId(uuid4())
    current = _month(expenses="800")  # spike vs ~500 history
    history = {
        (2026, 4): _month(expenses="500"),
        (2026, 3): _month(expenses="500"),
        (2026, 2): _month(expenses="500"),
    }
    reader = _FakeBudgetReader(current, history)
    writer = _FakeAlertWriter()
    use_case = DetectShiftAlertsUseCase(budget_reader=reader, alert_writer=writer)

    await use_case(uid, 2026, 5)

    assert len(writer.calls) == 1
    called_uid, called_year, called_month, shifts = writer.calls[0]
    assert called_uid == uid
    assert (called_year, called_month) == (2026, 5)
    assert shifts  # non-empty detected shifts
    assert any(s.type in ("expense_spike", "category_spike") for s in shifts)


@pytest.mark.asyncio
async def test_no_write_when_current_month_empty() -> None:
    uid = UserId(uuid4())
    reader = _FakeBudgetReader(current=[], history={(2026, 4): _month("500")})
    writer = _FakeAlertWriter()
    use_case = DetectShiftAlertsUseCase(budget_reader=reader, alert_writer=writer)

    await use_case(uid, 2026, 5)

    assert writer.calls == []


@pytest.mark.asyncio
async def test_no_write_when_fewer_than_two_history_months() -> None:
    uid = UserId(uuid4())
    current = _month(expenses="800")
    history = {(2026, 4): _month(expenses="500")}  # only 1 non-empty month
    reader = _FakeBudgetReader(current, history)
    writer = _FakeAlertWriter()
    use_case = DetectShiftAlertsUseCase(budget_reader=reader, alert_writer=writer)

    await use_case(uid, 2026, 5)

    assert writer.calls == []


@pytest.mark.asyncio
async def test_no_write_when_no_shifts() -> None:
    """Flat spending across all months -> detector finds nothing -> no write."""
    uid = UserId(uuid4())
    current = _month(expenses="500")
    history = {
        (2026, 4): _month(expenses="500"),
        (2026, 3): _month(expenses="500"),
        (2026, 2): _month(expenses="500"),
    }
    reader = _FakeBudgetReader(current, history)
    writer = _FakeAlertWriter()
    use_case = DetectShiftAlertsUseCase(budget_reader=reader, alert_writer=writer)

    await use_case(uid, 2026, 5)

    assert writer.calls == []


@pytest.mark.asyncio
async def test_history_in_other_currency_is_excluded() -> None:
    """Primary currency = current[0].currency; history in a different currency is filtered out.

    Here all history is EUR while current is USD, so same_currency_history is empty
    (<2) and no shift can be computed -> no write.
    """
    uid = UserId(uuid4())
    current = _month(expenses="800", currency="USD")
    history = {
        (2026, 4): _month(expenses="500", currency="EUR"),
        (2026, 3): _month(expenses="500", currency="EUR"),
        (2026, 2): _month(expenses="500", currency="EUR"),
    }
    reader = _FakeBudgetReader(current, history)
    writer = _FakeAlertWriter()
    use_case = DetectShiftAlertsUseCase(budget_reader=reader, alert_writer=writer)

    await use_case(uid, 2026, 5)

    assert writer.calls == []
