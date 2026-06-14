import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.recurring.use_cases.fire_due_rules import FireDueRulesUseCase
from app.domain.entities.recurring_rule import RecurringRule
from app.domain.value_objects.enums import Recurrence, RecurringRuleStatus, TransactionType
from app.domain.value_objects.ids import RecurringRuleId, UserId
from app.domain.value_objects.money import Currency, Money


def _rule(
    recurrence: Recurrence = Recurrence.MONTHLY,
    next_fire_date: date = date(2026, 5, 1),
    day_of_month: int = 1,
) -> RecurringRule:
    return RecurringRule(
        id_=RecurringRuleId(uuid.uuid4()),
        user_id=UserId(uuid.uuid4()),
        amount=Money(amount=Decimal("1000.00"), currency=Currency("USD")),
        type_=TransactionType.INCOME,
        merchant="Salary",
        notes=None,
        category_id=None,
        recurrence=recurrence,
        day_of_month=day_of_month,
        day_of_week=None,
        month=None,
        start_date=date(2026, 1, 1),
        end_date=None,
        status=RecurringRuleStatus.ACTIVE,
        next_fire_date=next_fire_date,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_creates_transaction_and_advances_date() -> None:
    rule = _rule(next_fire_date=date(2026, 5, 1), day_of_month=1)
    repo = MagicMock()
    repo.fetch_due_for_update = AsyncMock(side_effect=[[rule], []])
    repo.save = AsyncMock()
    create_tx = AsyncMock()

    uc = FireDueRulesUseCase(repo=repo, create_transaction=create_tx)
    await uc(today=date(2026, 5, 21))

    assert create_tx.call_count == 1
    assert rule.next_fire_date == date(2026, 6, 1)


@pytest.mark.asyncio
async def test_missed_fire_jumps_to_future() -> None:
    # Rule was due 2026-03-01; today is 2026-05-21
    rule = _rule(next_fire_date=date(2026, 3, 1), day_of_month=1)
    repo = MagicMock()
    repo.fetch_due_for_update = AsyncMock(side_effect=[[rule], []])
    repo.save = AsyncMock()
    create_tx = AsyncMock()

    uc = FireDueRulesUseCase(repo=repo, create_transaction=create_tx)
    await uc(today=date(2026, 5, 21))

    # Fires once; next date is in the future
    assert create_tx.call_count == 1
    assert rule.next_fire_date > date(2026, 5, 21)


@pytest.mark.asyncio
async def test_pauses_rule_past_end_date() -> None:
    rule = _rule(next_fire_date=date(2026, 5, 1), day_of_month=1)
    rule.end_date = date(2026, 5, 15)
    repo = MagicMock()
    repo.fetch_due_for_update = AsyncMock(side_effect=[[rule], []])
    repo.save = AsyncMock()
    create_tx = AsyncMock()

    uc = FireDueRulesUseCase(repo=repo, create_transaction=create_tx)
    await uc(today=date(2026, 5, 21))

    assert rule.status == RecurringRuleStatus.PAUSED


@pytest.mark.asyncio
async def test_empty_batch_stops_loop() -> None:
    repo = MagicMock()
    repo.fetch_due_for_update = AsyncMock(return_value=[])
    create_tx = AsyncMock()

    uc = FireDueRulesUseCase(repo=repo, create_transaction=create_tx)
    await uc(today=date(2026, 5, 21))

    create_tx.assert_not_called()


@pytest.mark.asyncio
async def test_persistently_failing_rule_terminates_loop() -> None:
    """A rule that always raises must not spin forever; loop must exit."""
    bad_rule = _rule(next_fire_date=date(2026, 5, 1), day_of_month=1)
    good_rule = _rule(next_fire_date=date(2026, 5, 1), day_of_month=1)

    repo = MagicMock()
    # First batch returns both rules; subsequent batches return only the bad one
    # (simulating fetch_due_for_update still seeing the non-advanced bad rule).
    repo.fetch_due_for_update = AsyncMock(
        side_effect=[[bad_rule, good_rule], [bad_rule], [bad_rule], [bad_rule]]
    )
    repo.save = AsyncMock()

    async def create_tx_side_effect(cmd: object) -> None:
        if cmd.recurring_rule_id == bad_rule.id_:  # type: ignore[union-attr]
            raise RuntimeError("DB error")

    create_tx = AsyncMock(side_effect=create_tx_side_effect)

    uc = FireDueRulesUseCase(repo=repo, create_transaction=create_tx)
    await uc(today=date(2026, 5, 21))  # must not hang

    # Good rule was advanced; bad rule was not saved
    assert good_rule.next_fire_date > date(2026, 5, 21)
    assert bad_rule.next_fire_date == date(2026, 5, 1)
    # fetch_due_for_update called at most twice: once for both, once filtered-out → break
    assert repo.fetch_due_for_update.call_count == 2


@pytest.mark.asyncio
async def test_batch_cap_reached_exits_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """If _MAX_BATCHES is hit the loop exits without hanging."""
    import app.application.recurring.use_cases.fire_due_rules as mod

    monkeypatch.setattr(mod, "_MAX_BATCHES", 5)
    mock_logger = MagicMock()
    monkeypatch.setattr(mod, "logger", mock_logger)

    repo = MagicMock()
    repo.fetch_due_for_update = AsyncMock(side_effect=lambda **_kw: [_rule()])
    repo.save = AsyncMock()
    create_tx = AsyncMock(side_effect=RuntimeError("always fails"))

    uc = FireDueRulesUseCase(repo=repo, create_transaction=create_tx)
    await uc(today=date(2026, 5, 21))

    assert repo.fetch_due_for_update.call_count == 5
    mock_logger.warning.assert_called_once()
