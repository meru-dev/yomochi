from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.insights.budget_summary_reader import (
    SqlaBudgetSummaryReader,
)


class _CountingSession:
    def __init__(self) -> None:
        self.execute_calls = 0
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, *_a: object, **_kw: object) -> MagicMock:
        self.execute_calls += 1
        result = MagicMock()
        result.fetchall = MagicMock(return_value=[])
        return result


@pytest.mark.asyncio
async def test_read_history_months_issues_one_query_for_any_n() -> None:
    session = _CountingSession()
    reader = SqlaBudgetSummaryReader(session=session)  # type: ignore[arg-type]

    out = await reader.read_history_months(
        user_id=UserId(uuid4()),
        before_year=2026,
        before_month=6,
        n_months=4,
    )

    assert session.execute_calls == 1, "read_history_months must not N+1"
    # Every requested month present in result map, even when there's no data.
    assert set(out.keys()) == {(2026, 5), (2026, 4), (2026, 3), (2026, 2)}
    assert all(v == [] for v in out.values())


@pytest.mark.asyncio
async def test_read_history_months_bucket_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows must land in the right (year, month) bucket."""
    session = MagicMock()
    rows = [
        MagicMock(
            amount_value=100,
            currency_code="JPY",
            type=MagicMock(value="EXPENSE"),
            date=date(2026, 5, 15),
            category_label="food",
        ),
        MagicMock(
            amount_value=200,
            currency_code="JPY",
            type=MagicMock(value="EXPENSE"),
            date=date(2026, 3, 2),
            category_label=None,
        ),
    ]
    result = MagicMock()
    result.fetchall = MagicMock(return_value=rows)
    session.execute = AsyncMock(return_value=result)

    reader = SqlaBudgetSummaryReader(session=session)
    out = await reader.read_history_months(
        user_id=UserId(uuid4()),
        before_year=2026,
        before_month=6,
        n_months=4,
    )

    assert len(out[(2026, 5)]) == 1
    assert out[(2026, 5)][0].day_of_month == 15
    assert len(out[(2026, 3)]) == 1
    assert out[(2026, 3)][0].day_of_month == 2
    # Months without rows are still present, empty.
    assert out[(2026, 4)] == []
    assert out[(2026, 2)] == []
