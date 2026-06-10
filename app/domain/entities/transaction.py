from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as _date

from app.domain.entities.base import EntityMixin
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import CategoryId, RecurringRuleId, TransactionId, UserId
from app.domain.value_objects.money import Money


class _Unset:
    """Sentinel for fields not provided to apply_update."""


_UNSET = _Unset()


@dataclass(eq=False)
class Transaction(EntityMixin):
    id_: TransactionId
    user_id: UserId
    amount: Money
    date: _date
    type_: TransactionType
    merchant: str | None
    notes: str | None
    category_id: CategoryId | None
    created_at: datetime
    updated_at: datetime | None = None
    recurring_rule_id: RecurringRuleId | None = None

    def apply_update(
        self,
        *,
        amount: Money | None = None,
        date: _date | None = None,
        type_: TransactionType | None = None,
        merchant: str | None | _Unset = _UNSET,
        notes: str | None | _Unset = _UNSET,
        category_id: CategoryId | None | _Unset = _UNSET,
    ) -> None:
        """Apply field updates. Only non-sentinel values are applied. Sets updated_at if anything changed."""
        changed = False
        if amount is not None:
            self.amount = amount
            changed = True
        if date is not None:
            self.date = date
            changed = True
        if type_ is not None:
            self.type_ = type_
            changed = True
        if not isinstance(merchant, _Unset):
            self.merchant = merchant
            changed = True
        if not isinstance(notes, _Unset):
            self.notes = notes
            changed = True
        if not isinstance(category_id, _Unset):
            self.category_id = category_id
            changed = True
        if changed:
            self.updated_at = datetime.now(UTC)
