from abc import abstractmethod
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import TransactionId, UserId


class TransactionRepository(Protocol):
    @abstractmethod
    async def save(self, transaction: Transaction) -> None: ...

    @abstractmethod
    async def get_by_id(
        self, transaction_id: TransactionId, user_id: UserId
    ) -> Transaction | None: ...

    @abstractmethod
    async def list_by_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[date, datetime, UUID] | None,
        type_filter: str | None = None,
        currency_filter: str | None = None,
        category_id_filter: str | None = None,
    ) -> list[Transaction]: ...

    @abstractmethod
    async def get_by_ids(self, ids: list[TransactionId], user_id: UserId) -> list[Transaction]: ...

    @abstractmethod
    async def delete(self, transaction_id: TransactionId, user_id: UserId) -> bool: ...
