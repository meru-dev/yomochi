import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.application.transactions.use_cases.get_transaction import (
    GetTransactionQuery,
    GetTransactionUseCase,
    TransactionNotFoundError,
)
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from app.domain.value_objects.money import Currency, Money
from tests.fakes.repositories import FakeTransactionRepository


def _make_tx(user_id: UserId) -> Transaction:
    return Transaction(
        id_=TransactionId(uuid.uuid4()),
        user_id=user_id,
        amount=Money(amount=Decimal("9.99"), currency=Currency("GBP")),
        date=date(2026, 5, 1),
        type_=TransactionType.EXPENSE,
        merchant="Shop",
        notes=None,
        category_id=None,
        created_at=datetime.now(UTC),
    )


async def test_returns_transaction() -> None:
    repo = FakeTransactionRepository()
    uc = GetTransactionUseCase(transaction_repo=repo)
    user = UserId(uuid.uuid4())
    tx = _make_tx(user)
    await repo.save(tx)

    result = await uc(GetTransactionQuery(transaction_id=tx.id_, user_id=user))

    assert result.id_ == tx.id_


async def test_raises_if_not_found() -> None:
    repo = FakeTransactionRepository()
    uc = GetTransactionUseCase(transaction_repo=repo)

    with pytest.raises(TransactionNotFoundError):
        await uc(
            GetTransactionQuery(
                transaction_id=TransactionId(uuid.uuid4()),
                user_id=UserId(uuid.uuid4()),
            )
        )


async def test_raises_if_belongs_to_other_user() -> None:
    repo = FakeTransactionRepository()
    uc = GetTransactionUseCase(transaction_repo=repo)
    owner = UserId(uuid.uuid4())
    other = UserId(uuid.uuid4())
    tx = _make_tx(owner)
    await repo.save(tx)

    with pytest.raises(TransactionNotFoundError):
        await uc(GetTransactionQuery(transaction_id=tx.id_, user_id=other))
