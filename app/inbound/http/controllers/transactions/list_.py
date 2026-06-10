from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Query, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.transactions.use_cases.list_transactions import (
    ListTransactionsQuery,
    ListTransactionsUseCase,
)
from app.domain.entities.transaction import Transaction

router = ErrorAwareRouter()


class TransactionListItem(BaseModel):
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


class ListTransactionsResponse(BaseModel):
    items: list[TransactionListItem]
    next_cursor: str | None


def _serialize(tx: Transaction) -> TransactionListItem:
    return TransactionListItem(
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


@router.get("", status_code=status.HTTP_200_OK, response_model=ListTransactionsResponse)
@inject
async def list_transactions(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ListTransactionsUseCase],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    type: str | None = Query(default=None),  # noqa: A002
    currency: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
) -> ListTransactionsResponse:
    result = await use_case(
        ListTransactionsQuery(
            user_id=identity.user_id,
            limit=limit,
            cursor=cursor,
            type_filter=type,
            currency_filter=currency,
            category_id_filter=category_id,
        )
    )
    return ListTransactionsResponse(
        items=[_serialize(tx) for tx in result.transactions],
        next_cursor=result.next_cursor,
    )
