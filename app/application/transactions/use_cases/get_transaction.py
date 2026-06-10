from dataclasses import dataclass

from app.application.transactions.ports.transaction_repository import TransactionRepository
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import TransactionId, UserId


class TransactionNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GetTransactionQuery:
    transaction_id: TransactionId
    user_id: UserId


class GetTransactionUseCase:
    def __init__(self, transaction_repo: TransactionRepository) -> None:
        self._transaction_repo = transaction_repo

    async def __call__(self, query: GetTransactionQuery) -> Transaction:
        transaction = await self._transaction_repo.get_by_id(
            transaction_id=query.transaction_id,
            user_id=query.user_id,
        )
        if transaction is None:
            raise TransactionNotFoundError(str(query.transaction_id))
        return transaction
