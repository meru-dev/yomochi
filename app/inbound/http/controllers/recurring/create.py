from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel, field_validator

from app.application.common.ports.identity_context import IdentityContext
from app.application.recurring.use_cases.create_recurring_rule import (
    CreateRecurringRuleCommand,
    CreateRecurringRuleUseCase,
)

router = ErrorAwareRouter()


class CreateRecurringRuleRequest(BaseModel):
    amount: str
    currency: str
    type: Literal["income", "expense"]
    recurrence: Literal["weekly", "monthly", "yearly"]
    start_date: date
    day_of_month: int | None = None
    day_of_week: int | None = None
    month: int | None = None
    merchant: str | None = None
    notes: str | None = None
    category_id: UUID | None = None
    end_date: date | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            Decimal(v)
        except InvalidOperation as exc:
            raise ValueError("Amount must be a valid number") from exc
        return v


class CreateRecurringRuleResponse(BaseModel):
    id: str


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateRecurringRuleResponse)
@inject
async def create_recurring_rule(
    body: CreateRecurringRuleRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[CreateRecurringRuleUseCase],
) -> CreateRecurringRuleResponse:
    result = await use_case(
        CreateRecurringRuleCommand(
            user_id=identity.user_id,
            raw_amount=body.amount,
            currency=body.currency,
            type_=body.type,
            recurrence=body.recurrence,
            start_date=body.start_date,
            day_of_month=body.day_of_month,
            day_of_week=body.day_of_week,
            month=body.month,
            merchant=body.merchant,
            notes=body.notes,
            raw_category_id=str(body.category_id) if body.category_id else None,
            end_date=body.end_date,
        )
    )
    return CreateRecurringRuleResponse(id=result.rule_id)
