from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.application.common.outbox_event import OutboxEvent
from app.application.common.ports.outbox_repository import OutboxRepository
from app.application.transactions.ports.category_list_reader import CategoryListReader
from app.application.transactions.ports.dirty_period_marker import DirtyPeriodMarker
from app.application.transactions.ports.transaction_repository import TransactionRepository
from app.application.transactions.use_cases.get_transaction import TransactionNotFoundError
from app.domain.entities.transaction import _UNSET
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import CategoryId, TransactionId, UserId
from app.domain.value_objects.money import Currency, Money


@dataclass(frozen=True, slots=True)
class UpdateTransactionCommand:
    user_id: UserId
    transaction_id: str
    fields_to_update: frozenset[str] = field(default_factory=frozenset)
    raw_amount: str | None = None
    currency: str | None = None
    date_: date | None = None
    type_: str | None = None
    merchant: str | None = None
    notes: str | None = None
    raw_category_id: str | None = None


class UpdateTransactionUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository,
        outbox_repo: OutboxRepository,
        dirty_period_marker: DirtyPeriodMarker,
        category_list_reader: CategoryListReader,
    ) -> None:
        self._transaction_repo = transaction_repo
        self._outbox_repo = outbox_repo
        self._dirty_period_marker = dirty_period_marker
        self._category_list_reader = category_list_reader

    async def __call__(self, command: UpdateTransactionCommand) -> None:
        if not command.fields_to_update:
            return  # no-op: nothing to update

        tx_id = TransactionId(UUID(command.transaction_id))
        transaction = await self._transaction_repo.get_by_id(tx_id, command.user_id)
        if transaction is None:
            raise TransactionNotFoundError

        old_date = transaction.date
        fields = command.fields_to_update

        if "category_id" in fields and command.raw_category_id is not None:
            _cat_id = CategoryId(UUID(command.raw_category_id))
            _cat = await self._category_list_reader.get_by_id_for_user(_cat_id, command.user_id)
            if _cat is not None:
                _cat.validate_assignable()

        amount: Money | None = None
        if "amount" in fields or "currency" in fields:
            cur = Currency(command.currency) if command.currency else transaction.amount.currency
            if command.raw_amount:
                amount = Money.from_string(command.raw_amount, cur)
            else:
                amount = Money(amount=transaction.amount.amount, currency=cur)

        transaction.apply_update(
            amount=amount,
            date=command.date_ if "date" in fields else None,
            type_=TransactionType(command.type_) if "type" in fields and command.type_ else None,
            merchant=command.merchant if "merchant" in fields else _UNSET,
            notes=command.notes if "notes" in fields else _UNSET,
            category_id=(
                CategoryId(UUID(command.raw_category_id)) if command.raw_category_id else None
            )
            if "category_id" in fields
            else _UNSET,
        )

        await self._transaction_repo.save(transaction)
        # Mark the new month dirty when date moves to a different (year, month)
        if "date" in fields and command.date_ is not None:
            new_d = command.date_
            if (new_d.year, new_d.month) != (old_date.year, old_date.month):
                await self._dirty_period_marker.mark_dirty(
                    transaction.user_id, new_d.year, new_d.month
                )
        payload: dict[str, Any] = {"transaction_date": transaction.date.isoformat()}
        if transaction.date != old_date:
            payload["old_date"] = old_date.isoformat()
        await self._outbox_repo.append(
            OutboxEvent(
                event_type="TransactionUpdated",
                aggregate_id=str(transaction.id_),
                payload=payload,
                occurred_at=datetime.now(UTC),
                user_id=transaction.user_id.value,
            )
        )
