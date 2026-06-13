from datetime import date

import structlog

from app.application.recurring.next_fire_date import advance_next_fire_date
from app.application.recurring.ports.recurring_rule_repository import RecurringRuleRepository
from app.application.transactions.use_cases.create_transaction import (
    CreateTransactionCommand,
    CreateTransactionUseCase,
)
from app.domain.entities.recurring_rule import RecurringRule
from app.domain.value_objects.ids import RecurringRuleId

logger = structlog.get_logger(__name__)

_BATCH = 50
_MAX_BATCHES = 100


class FireDueRulesUseCase:
    def __init__(
        self,
        repo: RecurringRuleRepository,
        create_transaction: CreateTransactionUseCase,
    ) -> None:
        self._repo = repo
        self._create_tx = create_transaction

    async def __call__(self, today: date) -> None:
        failed: set[RecurringRuleId] = set()
        for batch_num in range(_MAX_BATCHES):
            rules = await self._repo.fetch_due_for_update(as_of=today, limit=_BATCH)
            if not rules:
                break
            pending = [r for r in rules if r.id_ not in failed]
            if not pending:
                break
            fired = 0
            for rule in pending:
                ok = await self._fire(rule, today)
                if ok:
                    fired += 1
                else:
                    failed.add(rule.id_)
            logger.info("recurring_rules_fired", count=fired, batch=batch_num)
        else:
            logger.warning("recurring_fire_batch_cap_reached", cap=_MAX_BATCHES)

    async def _fire(self, rule: RecurringRule, today: date) -> bool:
        try:
            cmd = CreateTransactionCommand(
                user_id=rule.user_id,
                raw_amount=str(rule.amount.amount),
                currency=rule.amount.currency.code,
                date_=rule.next_fire_date,
                type_=rule.type_.value,
                merchant=rule.merchant,
                notes=rule.notes,
                raw_category_id=str(rule.category_id) if rule.category_id else None,
                recurring_rule_id=rule.id_,
            )
            await self._create_tx(cmd)
        except Exception:
            logger.exception("recurring_rule_fire_failed", rule_id=str(rule.id_))
            return False

        # Advance next_fire_date past today (skip missed periods)
        new_next = advance_next_fire_date(
            rule.next_fire_date,
            rule.recurrence,
            rule.day_of_month,
            rule.day_of_week,
            rule.month,
        )
        while new_next <= today:
            new_next = advance_next_fire_date(
                new_next, rule.recurrence, rule.day_of_month, rule.day_of_week, rule.month
            )
        rule.next_fire_date = new_next

        if rule.end_date is not None and rule.next_fire_date > rule.end_date:
            rule.pause()

        await self._repo.save(rule)
        return True
