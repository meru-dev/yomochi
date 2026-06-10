from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.recurring.use_cases.get_recurring_rule import (
    GetRecurringRuleQuery,
    GetRecurringRuleUseCase,
)
from app.application.recurring.use_cases.update_recurring_rule import (
    UpdateRecurringRuleCommand,
    UpdateRecurringRuleUseCase,
)
from app.domain.value_objects.ids import RecurringRuleId
from app.inbound.http.controllers.recurring.list_ import RecurringRuleItem, _serialize

router = ErrorAwareRouter()


class UpdateRecurringRuleRequest(BaseModel):
    status: str | None = None
    day_of_month: int | None = None
    day_of_week: int | None = None
    month: int | None = None
    merchant: str | None = None
    notes: str | None = None


@router.patch("/{rule_id}", status_code=status.HTTP_200_OK, response_model=RecurringRuleItem)
@inject
async def update_recurring_rule(
    rule_id: UUID,
    body: UpdateRecurringRuleRequest,
    identity: FromDishka[IdentityContext],
    update_uc: FromDishka[UpdateRecurringRuleUseCase],
    get_uc: FromDishka[GetRecurringRuleUseCase],
) -> RecurringRuleItem:
    rid = RecurringRuleId(rule_id)
    rule = await get_uc(GetRecurringRuleQuery(rule_id=rid, user_id=identity.user_id))
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    await update_uc(
        UpdateRecurringRuleCommand(
            rule_id=rid,
            user_id=identity.user_id,
            status=body.status,
            day_of_month=body.day_of_month,
            day_of_week=body.day_of_week,
            month=body.month,
            merchant=body.merchant,
            notes=body.notes,
        )
    )
    updated = await get_uc(GetRecurringRuleQuery(rule_id=rid, user_id=identity.user_id))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return _serialize(updated)
