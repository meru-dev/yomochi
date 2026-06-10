from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.domain.entities.base import EntityMixin
from app.domain.value_objects.enums import Recurrence, RecurringRuleStatus, TransactionType
from app.domain.value_objects.ids import CategoryId, RecurringRuleId, UserId
from app.domain.value_objects.money import Money


@dataclass(eq=False)
class RecurringRule(EntityMixin):
    id_: RecurringRuleId
    user_id: UserId
    amount: Money
    type_: TransactionType
    merchant: str | None
    notes: str | None
    category_id: CategoryId | None
    recurrence: Recurrence
    day_of_month: int | None
    day_of_week: int | None
    month: int | None
    start_date: date
    end_date: date | None
    status: RecurringRuleStatus
    next_fire_date: date
    created_at: datetime
    updated_at: datetime | None = None

    def pause(self) -> None:
        self.status = RecurringRuleStatus.PAUSED
        self.updated_at = datetime.now(UTC)

    def resume(self) -> None:
        self.status = RecurringRuleStatus.ACTIVE
        self.updated_at = datetime.now(UTC)
