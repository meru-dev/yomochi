from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from app.application.common.outbox_event import OutboxEvent
from app.application.common.ports.outbox_repository import OutboxRepository
from app.application.common.ports.quota_check import QuotaCheck, QuotaResource
from app.application.common.ports.user_plan_lookup import UserPlanLookup
from app.application.transactions.ports.category_list_reader import CategoryListReader
from app.application.transactions.ports.transaction_repository import TransactionRepository
from app.domain.entities.transaction import Transaction
from app.domain.ports.id_generator import TransactionIdGenerator
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import CategoryId, RecurringRuleId, UserId
from app.domain.value_objects.money import Currency, Money


@dataclass(frozen=True, slots=True)
class CreateTransactionCommand:
    user_id: UserId
    raw_amount: str
    currency: str
    date_: date
    type_: str
    merchant: str | None = None
    notes: str | None = None
    raw_category_id: str | None = None
    recurring_rule_id: RecurringRuleId | None = None


@dataclass(frozen=True, slots=True)
class CreateTransactionResult:
    transaction_id: str


class CreateTransactionUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository,
        outbox_repo: OutboxRepository,
        id_generator: TransactionIdGenerator,
        user_plan_lookup: UserPlanLookup,
        quota_check: QuotaCheck,
        category_list_reader: CategoryListReader,
    ) -> None:
        self._transaction_repo = transaction_repo
        self._outbox_repo = outbox_repo
        self._id_generator = id_generator
        self._user_plan_lookup = user_plan_lookup
        self._quota_check = quota_check
        self._category_list_reader = category_list_reader

    async def __call__(self, command: CreateTransactionCommand) -> CreateTransactionResult:
        plan = await self._user_plan_lookup.get_plan(command.user_id)
        await self._quota_check.check_and_increment(
            command.user_id, QuotaResource.TRANSACTIONS, plan
        )

        money = Money.from_string(command.raw_amount, Currency(command.currency))
        type_ = TransactionType(command.type_)

        category_id: CategoryId | None = (
            CategoryId(UUID(command.raw_category_id)) if command.raw_category_id else None
        )

        if category_id is not None:
            cat = await self._category_list_reader.get_by_id_for_user(category_id, command.user_id)
            if cat is not None:
                cat.validate_assignable()

        now = datetime.now(UTC)
        transaction = Transaction(
            id_=self._id_generator(),
            user_id=command.user_id,
            amount=money,
            date=command.date_,
            type_=type_,
            merchant=command.merchant,
            notes=command.notes,
            category_id=category_id,
            created_at=now,
            recurring_rule_id=command.recurring_rule_id,
        )
        await self._transaction_repo.save(transaction)
        await self._outbox_repo.append(
            OutboxEvent(
                event_type="TransactionCreated",
                aggregate_id=str(transaction.id_),
                payload={"transaction_date": command.date_.isoformat()},
                occurred_at=now,
                user_id=transaction.user_id.value,
            )
        )
        return CreateTransactionResult(transaction_id=str(transaction.id_))
