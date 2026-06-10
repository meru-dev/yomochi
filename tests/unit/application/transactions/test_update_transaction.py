import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import uuid_utils

from app.application.transactions.use_cases.get_transaction import TransactionNotFoundError
from app.application.transactions.use_cases.update_transaction import (
    UpdateTransactionCommand,
    UpdateTransactionUseCase,
)
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from app.domain.value_objects.money import Currency, Money
from tests.fakes.repositories import (
    FakeCategoryListReader,
    FakeOutboxRepository,
    FakeTransactionRepository,
)


def _make_tx(user_id: UserId) -> Transaction:
    return Transaction(
        id_=TransactionId(uuid.uuid4()),
        user_id=user_id,
        amount=Money(amount=Decimal("10.00"), currency=Currency("USD")),
        date=date(2026, 5, 1),
        type_=TransactionType.EXPENSE,
        merchant="Old merchant",
        notes=None,
        category_id=None,
        created_at=datetime.now(UTC),
    )


def _make_transaction(user_id: UserId, tx_id: TransactionId, date_: date) -> Transaction:
    return Transaction(
        id_=tx_id,
        user_id=user_id,
        amount=Money(Decimal("10"), Currency("USD")),
        date=date_,
        type_=TransactionType.EXPENSE,
        merchant=None,
        notes=None,
        category_id=None,
        created_at=datetime(2025, 1, 15, tzinfo=UTC),
    )


def _make_uc(
    repo: FakeTransactionRepository, outbox: FakeOutboxRepository
) -> UpdateTransactionUseCase:
    dirty_repo = AsyncMock()
    dirty_repo.mark_dirty = AsyncMock()
    return UpdateTransactionUseCase(
        transaction_repo=repo,
        outbox_repo=outbox,
        dirty_period_marker=dirty_repo,
        category_list_reader=FakeCategoryListReader(),
    )


async def test_updates_merchant() -> None:
    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    uc = _make_uc(repo, outbox)
    user = UserId(uuid.uuid4())
    tx = _make_tx(user)
    await repo.save(tx)

    await uc(
        UpdateTransactionCommand(
            user_id=user,
            transaction_id=str(tx.id_),
            fields_to_update=frozenset({"merchant"}),
            merchant="New merchant",
        )
    )

    updated = await repo.get_by_id(tx.id_, user)
    assert updated is not None
    assert updated.merchant == "New merchant"
    assert updated.updated_at is not None
    assert outbox.events[0].event_type == "TransactionUpdated"


async def test_clears_nullable_field() -> None:
    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    uc = _make_uc(repo, outbox)
    user = UserId(uuid.uuid4())
    tx = _make_tx(user)
    await repo.save(tx)

    await uc(
        UpdateTransactionCommand(
            user_id=user,
            transaction_id=str(tx.id_),
            fields_to_update=frozenset({"merchant"}),
            merchant=None,
        )
    )

    updated = await repo.get_by_id(tx.id_, user)
    assert updated is not None
    assert updated.merchant is None


async def test_raises_if_not_found() -> None:
    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    uc = _make_uc(repo, outbox)

    with pytest.raises(TransactionNotFoundError):
        await uc(
            UpdateTransactionCommand(
                user_id=UserId(uuid.uuid4()),
                transaction_id=str(uuid.uuid4()),
                fields_to_update=frozenset({"merchant"}),
                merchant="X",
            )
        )


async def test_cross_user_isolation() -> None:
    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    uc = _make_uc(repo, outbox)
    owner = UserId(uuid.uuid4())
    attacker = UserId(uuid.uuid4())
    tx = _make_tx(owner)
    await repo.save(tx)

    with pytest.raises(TransactionNotFoundError):
        await uc(
            UpdateTransactionCommand(
                user_id=attacker,
                transaction_id=str(tx.id_),
                fields_to_update=frozenset({"merchant"}),
                merchant="hacked",
            )
        )


@pytest.mark.asyncio
async def test_update_transaction_marks_period_dirty_on_month_change():
    user_id = UserId(uuid_utils.uuid7())
    tx_id = TransactionId(uuid_utils.uuid7())
    tx = _make_transaction(user_id, tx_id, date(2025, 1, 15))

    tx_repo = AsyncMock()
    tx_repo.get_by_id = AsyncMock(return_value=tx)
    tx_repo.save = AsyncMock()

    outbox_repo = AsyncMock()
    outbox_repo.append = AsyncMock()

    dirty_repo = AsyncMock()
    dirty_repo.mark_dirty = AsyncMock()

    use_case = UpdateTransactionUseCase(
        transaction_repo=tx_repo,
        outbox_repo=outbox_repo,
        dirty_period_marker=dirty_repo,
        category_list_reader=FakeCategoryListReader(),
    )

    cmd = UpdateTransactionCommand(
        user_id=user_id,
        transaction_id=str(tx_id.value),
        fields_to_update=frozenset({"date"}),
        date_=date(2025, 3, 10),
    )
    await use_case(cmd)

    dirty_repo.mark_dirty.assert_awaited_once_with(user_id, 2025, 3)


@pytest.mark.asyncio
async def test_update_transaction_no_dirty_when_same_month():
    user_id = UserId(uuid_utils.uuid7())
    tx_id = TransactionId(uuid_utils.uuid7())
    tx = _make_transaction(user_id, tx_id, date(2025, 1, 15))

    tx_repo = AsyncMock()
    tx_repo.get_by_id = AsyncMock(return_value=tx)
    tx_repo.save = AsyncMock()

    outbox_repo = AsyncMock()
    outbox_repo.append = AsyncMock()

    dirty_repo = AsyncMock()
    dirty_repo.mark_dirty = AsyncMock()

    use_case = UpdateTransactionUseCase(
        transaction_repo=tx_repo,
        outbox_repo=outbox_repo,
        dirty_period_marker=dirty_repo,
        category_list_reader=FakeCategoryListReader(),
    )

    cmd = UpdateTransactionCommand(
        user_id=user_id,
        transaction_id=str(tx_id.value),
        fields_to_update=frozenset({"date"}),
        date_=date(2025, 1, 25),  # same month
    )
    await use_case(cmd)

    dirty_repo.mark_dirty.assert_not_awaited()


async def test_update_raises_when_category_is_group() -> None:
    import uuid as _uuid
    from datetime import UTC
    from datetime import datetime as _datetime
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock

    from app.application.transactions.ports.category_list_reader import CategoryListItem
    from app.application.transactions.use_cases.update_transaction import UpdateTransactionCommand
    from app.domain.entities.transaction import Transaction
    from app.domain.exceptions.domain_errors import CategoryIsGroupError
    from app.domain.value_objects.enums import TransactionType
    from app.domain.value_objects.ids import TransactionId, UserId
    from app.domain.value_objects.money import Currency, Money
    from tests.fakes.repositories import (
        FakeCategoryListReader,
        FakeOutboxRepository,
        FakeTransactionRepository,
    )

    group_id = str(_uuid.uuid4())
    reader = FakeCategoryListReader()
    reader.seed([CategoryListItem(id_=group_id, name="Food & Drink", parent_id=None)])

    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    dirty = MagicMock()
    dirty.mark_dirty = AsyncMock(return_value=None)

    from app.application.transactions.use_cases.update_transaction import UpdateTransactionUseCase

    uc = UpdateTransactionUseCase(
        transaction_repo=repo,
        outbox_repo=outbox,
        dirty_period_marker=dirty,
        category_list_reader=reader,
    )

    user_id = UserId(_uuid.uuid4())
    tx = Transaction(
        id_=TransactionId(_uuid.uuid4()),
        user_id=user_id,
        amount=Money(amount=Decimal("100"), currency=Currency("JPY")),
        date=_datetime.now(UTC).date(),
        type_=TransactionType.EXPENSE,
        merchant=None,
        notes=None,
        category_id=None,
        recurring_rule_id=None,
        created_at=_datetime.now(UTC),
        updated_at=_datetime.now(UTC),
    )
    await repo.save(tx)

    with pytest.raises(CategoryIsGroupError):
        await uc(
            UpdateTransactionCommand(
                user_id=user_id,
                transaction_id=str(tx.id_.value),
                fields_to_update=frozenset(["category_id"]),
                raw_category_id=group_id,
            )
        )
