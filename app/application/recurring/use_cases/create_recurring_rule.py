from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from app.application.recurring.next_fire_date import compute_first_fire_date
from app.application.recurring.ports.recurring_rule_repository import RecurringRuleRepository
from app.domain.entities.recurring_rule import RecurringRule
from app.domain.exceptions.domain_errors import InvalidRecurrenceScheduleError
from app.domain.ports.id_generator import RecurringRuleIdGenerator
from app.domain.value_objects.enums import Recurrence, RecurringRuleStatus, TransactionType
from app.domain.value_objects.ids import CategoryId, UserId
from app.domain.value_objects.money import Currency, Money


@dataclass(frozen=True, slots=True)
class CreateRecurringRuleCommand:
    user_id: UserId
    raw_amount: str
    currency: str
    type_: str
    recurrence: str
    start_date: date
    day_of_month: int | None = None
    day_of_week: int | None = None
    month: int | None = None
    merchant: str | None = None
    notes: str | None = None
    raw_category_id: str | None = None
    end_date: date | None = None


@dataclass(frozen=True, slots=True)
class CreateRecurringRuleResult:
    rule_id: str


class CreateRecurringRuleUseCase:
    def __init__(
        self,
        repo: RecurringRuleRepository,
        id_generator: RecurringRuleIdGenerator,
    ) -> None:
        self._repo = repo
        self._id_generator = id_generator

    async def __call__(self, cmd: CreateRecurringRuleCommand) -> CreateRecurringRuleResult:
        amount = Money.from_string(cmd.raw_amount, Currency(cmd.currency))

        recurrence = Recurrence(cmd.recurrence)
        _validate_schedule(recurrence, cmd.day_of_month, cmd.day_of_week, cmd.month)

        first_fire = compute_first_fire_date(
            cmd.start_date, recurrence, cmd.day_of_month, cmd.day_of_week, cmd.month
        )
        category_id = CategoryId(UUID(cmd.raw_category_id)) if cmd.raw_category_id else None

        rule = RecurringRule(
            id_=self._id_generator(),
            user_id=cmd.user_id,
            amount=amount,
            type_=TransactionType(cmd.type_),
            merchant=cmd.merchant,
            notes=cmd.notes,
            category_id=category_id,
            recurrence=recurrence,
            day_of_month=cmd.day_of_month,
            day_of_week=cmd.day_of_week,
            month=cmd.month,
            start_date=cmd.start_date,
            end_date=cmd.end_date,
            status=RecurringRuleStatus.ACTIVE,
            next_fire_date=first_fire,
            created_at=datetime.now(UTC),
        )
        await self._repo.save(rule)
        return CreateRecurringRuleResult(rule_id=str(rule.id_))


def _validate_schedule(
    recurrence: Recurrence,
    day_of_month: int | None,
    day_of_week: int | None,
    month: int | None,
) -> None:
    if recurrence == Recurrence.WEEKLY:
        if day_of_week is None or not (0 <= day_of_week <= 6):
            raise InvalidRecurrenceScheduleError("WEEKLY requires day_of_week in 0–6")
    elif recurrence == Recurrence.MONTHLY:
        if day_of_month is None or not (1 <= day_of_month <= 28):
            raise InvalidRecurrenceScheduleError("MONTHLY requires day_of_month in 1–28")
    elif recurrence == Recurrence.YEARLY:
        if day_of_month is None or not (1 <= day_of_month <= 28):
            raise InvalidRecurrenceScheduleError("YEARLY requires day_of_month in 1–28")
        if month is None or not (1 <= month <= 12):
            raise InvalidRecurrenceScheduleError("YEARLY requires month in 1–12")
    else:
        raise InvalidRecurrenceScheduleError("Recurrence.NONE is not valid for RecurringRule")
