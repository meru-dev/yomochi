from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.recurring.next_fire_date import compute_first_fire_date
from app.application.recurring.ports.recurring_rule_repository import RecurringRuleRepository
from app.application.recurring.use_cases.create_recurring_rule import _validate_schedule
from app.domain.value_objects.enums import RecurringRuleStatus
from app.domain.value_objects.ids import RecurringRuleId, UserId


@dataclass(frozen=True, slots=True)
class UpdateRecurringRuleCommand:
    rule_id: RecurringRuleId
    user_id: UserId
    status: str | None = None
    day_of_month: int | None = None
    day_of_week: int | None = None
    month: int | None = None
    merchant: str | None = None
    notes: str | None = None


class UpdateRecurringRuleUseCase:
    def __init__(self, repo: RecurringRuleRepository) -> None:
        self._repo = repo

    async def __call__(self, cmd: UpdateRecurringRuleCommand) -> None:
        rule = await self._repo.get(cmd.rule_id, cmd.user_id)
        if rule is None:
            return  # 404 handled by controller

        changed = False

        if cmd.status is not None:
            new_status = RecurringRuleStatus(cmd.status)
            if new_status != rule.status:
                rule.status = new_status
                changed = True

        if cmd.merchant is not None:
            rule.merchant = cmd.merchant
            changed = True

        if cmd.notes is not None:
            rule.notes = cmd.notes
            changed = True

        schedule_changed = any(
            f is not None for f in [cmd.day_of_month, cmd.day_of_week, cmd.month]
        )
        if schedule_changed:
            dom = cmd.day_of_month if cmd.day_of_month is not None else rule.day_of_month
            dow = cmd.day_of_week if cmd.day_of_week is not None else rule.day_of_week
            mo = cmd.month if cmd.month is not None else rule.month
            _validate_schedule(rule.recurrence, dom, dow, mo)
            rule.day_of_month = dom
            rule.day_of_week = dow
            rule.month = mo
            rule.next_fire_date = compute_first_fire_date(
                datetime.now(UTC).date(), rule.recurrence, dom, dow, mo
            )
            changed = True

        if changed:
            rule.updated_at = datetime.now(UTC)
            await self._repo.save(rule)
