import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.application.transactions.use_cases.delete_transaction import (
    DeleteTransactionCommand,
    DeleteTransactionUseCase,
)
from app.application.transactions.use_cases.get_transaction import TransactionNotFoundError
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from app.domain.value_objects.money import Currency, Money
from tests.fakes.repositories import FakeAuditLog, FakeOutboxRepository, FakeTransactionRepository


def _make_tx(user_id: UserId) -> Transaction:
    return Transaction(
        id_=TransactionId(uuid.uuid4()),
        user_id=user_id,
        amount=Money(amount=Decimal("5.00"), currency=Currency("USD")),
        date=date(2026, 5, 1),
        type_=TransactionType.EXPENSE,
        merchant=None,
        notes=None,
        category_id=None,
        created_at=datetime.now(UTC),
    )


def _make_dirty_marker() -> AsyncMock:
    m = AsyncMock()
    m.mark_dirty = AsyncMock()
    return m


def _make_uc(
    repo: FakeTransactionRepository, outbox: FakeOutboxRepository
) -> DeleteTransactionUseCase:
    return DeleteTransactionUseCase(
        transaction_repo=repo,
        outbox_repo=outbox,
        dirty_period_marker=_make_dirty_marker(),  # type: ignore[arg-type]
        audit_log=FakeAuditLog(),
    )


async def test_deletes_transaction() -> None:
    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    uc = _make_uc(repo, outbox)
    user = UserId(uuid.uuid4())
    tx = _make_tx(user)
    await repo.save(tx)

    await uc(DeleteTransactionCommand(transaction_id=tx.id_, user_id=user))

    assert await repo.get_by_id(tx.id_, user) is None
    assert len(outbox.events) == 1
    assert outbox.events[0].event_type == "TransactionDeleted"


async def test_raises_if_not_found() -> None:
    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    uc = _make_uc(repo, outbox)

    with pytest.raises(TransactionNotFoundError):
        await uc(
            DeleteTransactionCommand(
                transaction_id=TransactionId(uuid.uuid4()),
                user_id=UserId(uuid.uuid4()),
            )
        )


async def test_raises_if_belongs_to_other_user() -> None:
    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    uc = _make_uc(repo, outbox)
    owner = UserId(uuid.uuid4())
    other = UserId(uuid.uuid4())
    tx = _make_tx(owner)
    await repo.save(tx)

    with pytest.raises(TransactionNotFoundError):
        await uc(DeleteTransactionCommand(transaction_id=tx.id_, user_id=other))

    assert await repo.get_by_id(tx.id_, owner) is not None
