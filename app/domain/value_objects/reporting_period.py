from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Literal

Granularity = Literal["month", "week"]


@dataclass(frozen=True, slots=True)
class MonthPeriod:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"month out of range: {self.month}")
        if self.year < 1900 or self.year > 2999:
            raise ValueError(f"year out of range: {self.year}")

    def bounds_clipped_to(self, today: date) -> tuple[date, date]:
        """Inclusive [start, end] for this calendar month, end clipped to today."""
        start = date(self.year, self.month, 1)
        last_day = monthrange(self.year, self.month)[1]
        natural_end = date(self.year, self.month, last_day)
        return start, min(natural_end, today)


@dataclass(frozen=True, slots=True)
class TrendWindow:
    granularity: Granularity
    bucket_count: int
    end: date

    def __post_init__(self) -> None:
        if self.granularity not in ("month", "week"):
            raise ValueError(f"granularity must be month|week, got {self.granularity}")
        if not 1 <= self.bucket_count <= 52:
            raise ValueError(f"bucket_count out of range: {self.bucket_count}")
