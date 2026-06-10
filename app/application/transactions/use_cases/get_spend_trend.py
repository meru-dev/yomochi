from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.application.transactions.ports.spend_trend_reader import (
    SpendTrendReader,
    TrendBucket,
)
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.money import Currency
from app.domain.value_objects.reporting_period import TrendWindow


@dataclass(frozen=True, slots=True)
class GetSpendTrendCommand:
    user_id: UserId
    currency: str
    type_: str
    bucket_count: int
    granularity: Literal["month", "week"]


@dataclass(frozen=True, slots=True)
class SpendTrendResult:
    buckets: list[TrendBucket]


class GetSpendTrendUseCase:
    def __init__(self, reader: SpendTrendReader) -> None:
        self._reader = reader

    async def __call__(self, command: GetSpendTrendCommand) -> SpendTrendResult:
        today = datetime.now(UTC).date()
        window = TrendWindow(
            granularity=command.granularity,
            bucket_count=command.bucket_count,
            end=today,
        )
        buckets = await self._reader.read(
            user_id=command.user_id,
            currency=Currency(command.currency),
            type_=TransactionType(command.type_),
            window=window,
        )
        return SpendTrendResult(buckets=buckets)
