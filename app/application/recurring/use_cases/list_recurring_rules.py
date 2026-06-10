from dataclasses import dataclass

from app.application.recurring.ports.recurring_rule_repository import RecurringRuleRepository
from app.domain.entities.recurring_rule import RecurringRule
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class ListRecurringRulesQuery:
    user_id: UserId


class ListRecurringRulesUseCase:
    def __init__(self, repo: RecurringRuleRepository) -> None:
        self._repo = repo

    async def __call__(self, query: ListRecurringRulesQuery) -> list[RecurringRule]:
        return await self._repo.list_(query.user_id)
