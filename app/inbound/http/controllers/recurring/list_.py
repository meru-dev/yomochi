from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.recurring.use_cases.list_recurring_rules import (
    ListRecurringRulesQuery,
    ListRecurringRulesUseCase,
)
from app.domain.entities.recurring_rule import RecurringRule

router = ErrorAwareRouter()


class RecurringRuleItem(BaseModel):
    id: str
    amount: str
    currency: str
    type: str
    recurrence: str
    day_of_month: int | None
    day_of_week: int | None
    month: int | None
    merchant: str | None
    notes: str | None
    category_id: str | None
    start_date: str
    end_date: str | None
    status: str
    next_fire_date: str
    created_at: str


class ListRecurringRulesResponse(BaseModel):
    items: list[RecurringRuleItem]


def _serialize(rule: RecurringRule) -> RecurringRuleItem:
    return RecurringRuleItem(
        id=str(rule.id_),
        amount=str(rule.amount.amount),
        currency=rule.amount.currency.code,
        type=rule.type_.value,
        recurrence=rule.recurrence.value,
        day_of_month=rule.day_of_month,
        day_of_week=rule.day_of_week,
        month=rule.month,
        merchant=rule.merchant,
        notes=rule.notes,
        category_id=str(rule.category_id) if rule.category_id else None,
        start_date=rule.start_date.isoformat(),
        end_date=rule.end_date.isoformat() if rule.end_date else None,
        status=rule.status.value,
        next_fire_date=rule.next_fire_date.isoformat(),
        created_at=rule.created_at.isoformat(),
    )


@router.get("", status_code=status.HTTP_200_OK, response_model=ListRecurringRulesResponse)
@inject
async def list_recurring_rules(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ListRecurringRulesUseCase],
) -> ListRecurringRulesResponse:
    rules = await use_case(ListRecurringRulesQuery(user_id=identity.user_id))
    return ListRecurringRulesResponse(items=[_serialize(r) for r in rules])
