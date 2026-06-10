from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.transactions.use_cases.get_transaction import (
    GetTransactionQuery,
    GetTransactionUseCase,
)
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import TransactionId

router = ErrorAwareRouter()


class TransactionResponse(BaseModel):
    id: str
    amount: str
    currency: str
    date: str
    type: str
    merchant: str | None
    notes: str | None
    category_id: str | None
    recurring_rule_id: str | None
    created_at: str
    updated_at: str | None


def _serialize(tx: Transaction) -> TransactionResponse:
    return TransactionResponse(
        id=str(tx.id_),
        amount=str(tx.amount.amount),
        currency=tx.amount.currency.code,
        date=tx.date.isoformat(),
        type=tx.type_.value,
        merchant=tx.merchant,
        notes=tx.notes,
        category_id=str(tx.category_id) if tx.category_id else None,
        recurring_rule_id=str(tx.recurring_rule_id) if tx.recurring_rule_id else None,
        created_at=tx.created_at.isoformat(),
        updated_at=tx.updated_at.isoformat() if tx.updated_at else None,
    )


@router.get("/{transaction_id}", status_code=status.HTTP_200_OK, response_model=TransactionResponse)
@inject
async def get_transaction(
    transaction_id: UUID,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[GetTransactionUseCase],
) -> TransactionResponse:
    transaction = await use_case(
        GetTransactionQuery(
            transaction_id=TransactionId(transaction_id),
            user_id=identity.user_id,
        )
    )
    return _serialize(transaction)
