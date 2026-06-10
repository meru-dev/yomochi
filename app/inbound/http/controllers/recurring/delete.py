from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, status
from fastapi_error_map import ErrorAwareRouter

from app.application.common.ports.identity_context import IdentityContext
from app.application.recurring.use_cases.delete_recurring_rule import (
    DeleteRecurringRuleCommand,
    DeleteRecurringRuleUseCase,
)
from app.application.recurring.use_cases.get_recurring_rule import (
    GetRecurringRuleQuery,
    GetRecurringRuleUseCase,
)
from app.domain.value_objects.ids import RecurringRuleId

router = ErrorAwareRouter()


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_recurring_rule(
    rule_id: UUID,
    identity: FromDishka[IdentityContext],
    delete_uc: FromDishka[DeleteRecurringRuleUseCase],
    get_uc: FromDishka[GetRecurringRuleUseCase],
) -> None:
    rid = RecurringRuleId(rule_id)
    rule = await get_uc(GetRecurringRuleQuery(rule_id=rid, user_id=identity.user_id))
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    await delete_uc(DeleteRecurringRuleCommand(rule_id=rid, user_id=identity.user_id))
