import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.entities.recurring_rule import RecurringRule
from app.domain.value_objects.enums import Recurrence, RecurringRuleStatus, TransactionType
from app.domain.value_objects.ids import RecurringRuleId, UserId
from app.domain.value_objects.money import Currency, Money


def _rule() -> RecurringRule:
    return RecurringRule(
        id_=RecurringRuleId(uuid.uuid4()),
        user_id=UserId(uuid.uuid4()),
        amount=Money(amount=Decimal("100.00"), currency=Currency("USD")),
        type_=TransactionType.INCOME,
        merchant="Employer",
        notes=None,
        category_id=None,
        recurrence=Recurrence.MONTHLY,
        day_of_month=1,
        day_of_week=None,
        month=None,
        start_date=date(2026, 6, 1),
        end_date=None,
        status=RecurringRuleStatus.ACTIVE,
        next_fire_date=date(2026, 6, 1),
        created_at=datetime.now(UTC),
    )


def test_pause_sets_status_paused() -> None:
    rule = _rule()
    rule.pause()
    assert rule.status == RecurringRuleStatus.PAUSED
    assert rule.updated_at is not None


def test_resume_sets_status_active() -> None:
    rule = _rule()
    rule.pause()
    rule.resume()
    assert rule.status == RecurringRuleStatus.ACTIVE


def test_equality_by_id() -> None:
    rule = _rule()
    other = _rule()
    assert rule != other  # different ids
    assert rule == rule
