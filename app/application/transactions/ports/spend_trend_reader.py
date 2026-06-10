from abc import abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.money import Currency
from app.domain.value_objects.reporting_period import TrendWindow


@dataclass(frozen=True, slots=True)
class TrendBucket:
    label: str  # "YYYY-MM" for month, "YYYY-Www" (ISO year-week) for week
    total: Decimal


class SpendTrendReader(Protocol):
    @abstractmethod
    async def read(
        self,
        user_id: UserId,
        currency: Currency,
        type_: TransactionType,
        window: TrendWindow,
    ) -> list[TrendBucket]: ...
