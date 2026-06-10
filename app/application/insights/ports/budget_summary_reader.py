from abc import abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.domain.value_objects.ids import UserId


@dataclass(frozen=True)
class BudgetTransactionRow:
    amount: Decimal
    currency: str
    type_: str  # "income" | "expense"
    category_label: str | None
    day_of_month: int


class BudgetSummaryReader(Protocol):
    @abstractmethod
    async def read_month(
        self,
        user_id: UserId,
        year: int,
        month: int,
    ) -> list[BudgetTransactionRow]: ...

    @abstractmethod
    async def read_history_months(
        self,
        user_id: UserId,
        before_year: int,
        before_month: int,
        n_months: int,
    ) -> dict[tuple[int, int], list[BudgetTransactionRow]]: ...
