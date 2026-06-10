from dataclasses import dataclass

from app.application.recurring.ports.recurring_rule_repository import RecurringRuleRepository
from app.domain.value_objects.ids import RecurringRuleId, UserId


@dataclass(frozen=True, slots=True)
class DeleteRecurringRuleCommand:
    rule_id: RecurringRuleId
    user_id: UserId


class DeleteRecurringRuleUseCase:
    def __init__(self, repo: RecurringRuleRepository) -> None:
        self._repo = repo

    async def __call__(self, cmd: DeleteRecurringRuleCommand) -> None:
        await self._repo.delete(cmd.rule_id, cmd.user_id)
