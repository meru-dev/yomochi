from datetime import date as _Date  # noqa: N812
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel, field_validator

from app.application.common.ports.identity_context import IdentityContext
from app.application.transactions.use_cases.update_transaction import (
    UpdateTransactionCommand,
    UpdateTransactionUseCase,
)

router = ErrorAwareRouter()


class UpdateTransactionRequest(BaseModel):
    amount: str | None = None
    currency: str | None = None
    date: _Date | None = None
    type: Literal["expense", "income"] | None = None
    merchant: str | None = None
    notes: str | None = None
    category_id: UUID | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            Decimal(v)
        except InvalidOperation as exc:
            raise ValueError("Amount must be a valid number") from exc
        return v


@router.patch("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def update_transaction(
    transaction_id: UUID,
    body: UpdateTransactionRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[UpdateTransactionUseCase],
) -> None:
    await use_case(
        UpdateTransactionCommand(
            user_id=identity.user_id,
            transaction_id=str(transaction_id),
            fields_to_update=frozenset(body.model_fields_set),
            raw_amount=body.amount,
            currency=body.currency,
            date_=body.date,
            type_=body.type,
            merchant=body.merchant,
            notes=body.notes,
            raw_category_id=str(body.category_id) if body.category_id else None,
        )
    )
