import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.transactions.use_cases.list_transactions import (
    ListTransactionsQuery,
    ListTransactionsUseCase,
)
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from app.domain.value_objects.money import Currency, Money
from tests.fakes.repositories import FakeTransactionRepository


def _make_tx(user_id: UserId, txn_date: date, created_at: datetime | None = None) -> Transaction:
    return Transaction(
        id_=TransactionId(uuid.uuid4()),
        user_id=user_id,
        amount=Money(amount=Decimal("10.00"), currency=Currency("USD")),
        date=txn_date,
        type_=TransactionType.EXPENSE,
        merchant=None,
        notes=None,
        category_id=None,
        created_at=created_at or datetime.now(UTC),
    )


async def test_returns_only_user_transactions() -> None:
    repo = FakeTransactionRepository()
    uc = ListTransactionsUseCase(transaction_repo=repo)
    user_a = UserId(uuid.uuid4())
    user_b = UserId(uuid.uuid4())

    tx_a = _make_tx(user_a, date(2026, 5, 1))
    tx_b = _make_tx(user_b, date(2026, 5, 2))
    await repo.save(tx_a)
    await repo.save(tx_b)

    result = await uc(ListTransactionsQuery(user_id=user_a))

    assert len(result.transactions) == 1
    assert result.transactions[0].id_ == tx_a.id_


async def test_cursor_pagination() -> None:
    repo = FakeTransactionRepository()
    uc = ListTransactionsUseCase(transaction_repo=repo)
    user = UserId(uuid.uuid4())

    txs = []
    for d in range(1, 6):
        tx = _make_tx(user, date(2026, 5, d))
        await repo.save(tx)
        txs.append(tx)

    page1 = await uc(ListTransactionsQuery(user_id=user, limit=2))
    assert len(page1.transactions) == 2
    assert page1.next_cursor is not None

    page2 = await uc(ListTransactionsQuery(user_id=user, limit=2, cursor=page1.next_cursor))
    assert len(page2.transactions) == 2

    ids1 = {tx.id_ for tx in page1.transactions}
    ids2 = {tx.id_ for tx in page2.transactions}
    assert ids1.isdisjoint(ids2)


async def test_no_next_cursor_on_last_page() -> None:
    repo = FakeTransactionRepository()
    uc = ListTransactionsUseCase(transaction_repo=repo)
    user = UserId(uuid.uuid4())

    for d in range(1, 4):
        await repo.save(_make_tx(user, date(2026, 5, d)))

    result = await uc(ListTransactionsQuery(user_id=user, limit=10))

    assert len(result.transactions) == 3
    assert result.next_cursor is None


async def test_returns_empty_for_unknown_user() -> None:
    repo = FakeTransactionRepository()
    uc = ListTransactionsUseCase(transaction_repo=repo)

    result = await uc(ListTransactionsQuery(user_id=UserId(uuid.uuid4())))

    assert result.transactions == ()
    assert result.next_cursor is None
