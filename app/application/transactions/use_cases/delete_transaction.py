from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.common.audit_event import AuditEvent
from app.application.common.outbox_event import OutboxEvent
from app.application.common.ports.audit_log import AuditLog
from app.application.common.ports.outbox_repository import OutboxRepository
from app.application.transactions.ports.dirty_period_marker import DirtyPeriodMarker
from app.application.transactions.ports.transaction_repository import TransactionRepository
from app.application.transactions.use_cases.get_transaction import TransactionNotFoundError
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import TransactionId, UserId


@dataclass(frozen=True, slots=True)
class DeleteTransactionCommand:
    transaction_id: TransactionId
    user_id: UserId


class DeleteTransactionUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository,
        outbox_repo: OutboxRepository,
        dirty_period_marker: DirtyPeriodMarker,
        audit_log: AuditLog,
    ) -> None:
        self._transaction_repo = transaction_repo
        self._outbox_repo = outbox_repo
        self._dirty_period_marker = dirty_period_marker
        self._audit_log = audit_log

    async def __call__(self, command: DeleteTransactionCommand) -> None:
        transaction = await self._transaction_repo.get_by_id(
            command.transaction_id, command.user_id
        )
        if transaction is None:
            raise TransactionNotFoundError(str(command.transaction_id))
        transaction_date = transaction.date
        await self._transaction_repo.delete(
            transaction_id=command.transaction_id,
            user_id=command.user_id,
        )
        now = datetime.now(UTC)
        await self._dirty_period_marker.mark_dirty(
            command.user_id, transaction_date.year, transaction_date.month
        )
        await self._outbox_repo.append(
            OutboxEvent(
                event_type="TransactionDeleted",
                aggregate_id=str(command.transaction_id),
                payload={"transaction_date": transaction_date.isoformat()},
                occurred_at=now,
                user_id=command.user_id.value,
            )
        )
        await self._audit_log.record(
            AuditEvent(
                event_type=AuditEventType.TRANSACTION_DELETED,
                user_id=command.user_id,
                occurred_at=now,
            )
        )
