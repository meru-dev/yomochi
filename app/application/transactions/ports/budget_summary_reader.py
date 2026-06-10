from abc import abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.reporting_period import MonthPeriod


@dataclass(frozen=True, slots=True)
class CurrencyTotalRow:
    currency: str
    type_: TransactionType
    total: Decimal
    count: int


class BudgetSummaryReader(Protocol):
    @abstractmethod
    async def read_clipped(
        self,
        user_id: UserId,
        period: MonthPeriod,
        clipped_to: date,
    ) -> list[CurrencyTotalRow]: ...
