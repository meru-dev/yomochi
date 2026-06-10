from abc import abstractmethod
from typing import Protocol

from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import TransactionId, UserId


class TransactionReader(Protocol):
    @abstractmethod
    async def get_by_ids(self, ids: list[TransactionId], user_id: UserId) -> list[Transaction]: ...
