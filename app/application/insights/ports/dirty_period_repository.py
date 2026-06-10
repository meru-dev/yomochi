from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.ids import UserId


class DirtyPeriod:
    __slots__ = ("month", "user_id", "year")

    def __init__(self, user_id: UserId, year: int, month: int) -> None:
        self.user_id = user_id
        self.year = year
        self.month = month


class DirtyPeriodRepository(Protocol):
    @abstractmethod
    async def mark_dirty(self, user_id: UserId, year: int, month: int) -> None: ...

    @abstractmethod
    async def pop_dirty(self, limit: int = 100) -> list[DirtyPeriod]: ...
