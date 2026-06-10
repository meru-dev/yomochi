from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from app.domain.value_objects.ids import UserId


class SearchCache(Protocol):
    @abstractmethod
    async def get(self, user_id: UserId, query: str) -> list[UUID] | None: ...

    @abstractmethod
    async def set(self, user_id: UserId, query: str, transaction_ids: list[UUID]) -> None: ...
