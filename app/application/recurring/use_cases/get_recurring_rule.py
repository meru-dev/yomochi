from dataclasses import dataclass

from app.application.recurring.ports.recurring_rule_repository import RecurringRuleRepository
from app.domain.entities.recurring_rule import RecurringRule
from app.domain.value_objects.ids import RecurringRuleId, UserId


@dataclass(frozen=True, slots=True)
class GetRecurringRuleQuery:
    rule_id: RecurringRuleId
    user_id: UserId


class GetRecurringRuleUseCase:
    def __init__(self, repo: RecurringRuleRepository) -> None:
        self._repo = repo

    async def __call__(self, query: GetRecurringRuleQuery) -> RecurringRule | None:
        return await self._repo.get(query.rule_id, query.user_id)
