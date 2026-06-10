from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, status
from fastapi_error_map import ErrorAwareRouter

from app.application.common.ports.identity_context import IdentityContext
from app.application.recurring.use_cases.get_recurring_rule import (
    GetRecurringRuleQuery,
    GetRecurringRuleUseCase,
)
from app.domain.value_objects.ids import RecurringRuleId
from app.inbound.http.controllers.recurring.list_ import RecurringRuleItem, _serialize

router = ErrorAwareRouter()


@router.get("/{rule_id}", status_code=status.HTTP_200_OK, response_model=RecurringRuleItem)
@inject
async def get_recurring_rule(
    rule_id: UUID,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[GetRecurringRuleUseCase],
) -> RecurringRuleItem:
    rule = await use_case(
        GetRecurringRuleQuery(rule_id=RecurringRuleId(rule_id), user_id=identity.user_id)
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return _serialize(rule)
