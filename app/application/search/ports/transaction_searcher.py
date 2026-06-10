from abc import abstractmethod
from typing import Protocol

from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import UserId


class TransactionSearcher(Protocol):
    @abstractmethod
    async def search(self, user_id: UserId, query: str, limit: int = 20) -> list[Transaction]: ...
