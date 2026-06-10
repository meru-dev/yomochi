from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.ids import UserId


class PortraitQueue(Protocol):
    @abstractmethod
    async def pop_dirty(self, limit: int) -> list[UserId]: ...

    @abstractmethod
    async def mark_dirty(self, user_id: UserId) -> None: ...

    @abstractmethod
    async def mark_all_dirty(self) -> int: ...
