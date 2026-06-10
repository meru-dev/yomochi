from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel, field_validator

from app.application.common.ports.identity_context import IdentityContext
from app.application.transactions.use_cases.create_transaction import (
    CreateTransactionCommand,
    CreateTransactionUseCase,
)

router = ErrorAwareRouter()


class CreateTransactionRequest(BaseModel):
    amount: str
    currency: str
    date: date
    type: Literal["expense", "income"]
    merchant: str | None = None
    notes: str | None = None
    category_id: UUID | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            Decimal(v)
        except InvalidOperation as exc:
            raise ValueError("Amount must be a valid number") from exc
        return v


class CreateTransactionResponse(BaseModel):
    id: str


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateTransactionResponse)
@inject
async def create_transaction(
    body: CreateTransactionRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[CreateTransactionUseCase],
) -> CreateTransactionResponse:
    result = await use_case(
        CreateTransactionCommand(
            user_id=identity.user_id,
            raw_amount=body.amount,
            currency=body.currency,
            date_=body.date,
            type_=body.type,
            merchant=body.merchant,
            notes=body.notes,
            raw_category_id=str(body.category_id) if body.category_id else None,
        )
    )
    return CreateTransactionResponse(id=result.transaction_id)
