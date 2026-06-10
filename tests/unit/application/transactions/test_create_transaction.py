import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.transactions.use_cases.create_transaction import (
    CreateTransactionCommand,
    CreateTransactionUseCase,
)
from app.domain.exceptions.domain_errors import InvalidCurrencyError, InvalidMoneyError
from app.domain.value_objects.enums import Plan, TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from tests.fakes.id_generator import FakeTransactionIdGenerator
from tests.fakes.repositories import (
    FakeCategoryListReader,
    FakeOutboxRepository,
    FakeTransactionRepository,
)


def _user_id() -> UserId:
    return UserId(uuid.uuid4())


def _make_use_case() -> tuple[
    CreateTransactionUseCase, FakeTransactionRepository, FakeOutboxRepository
]:
    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()

    user_plan_lookup = MagicMock()
    user_plan_lookup.get_plan = AsyncMock(return_value=Plan.FREE)

    class _NoOpQuotaCheck:
        async def check_and_increment(self, *a: object, **kw: object) -> None: ...
        async def refund(self, *a: object, **kw: object) -> None: ...

    uc = CreateTransactionUseCase(
        transaction_repo=repo,
        outbox_repo=outbox,
        id_generator=FakeTransactionIdGenerator(),
        user_plan_lookup=user_plan_lookup,
        category_list_reader=FakeCategoryListReader(),
        quota_check=_NoOpQuotaCheck(),  # type: ignore[arg-type]
    )
    return uc, repo, outbox


async def test_creates_expense() -> None:
    uc, repo, outbox = _make_use_case()
    user_id = _user_id()

    result = await uc(
        CreateTransactionCommand(
            user_id=user_id,
            raw_amount="12.50",
            currency="USD",
            date_=date(2026, 5, 1),
            type_="expense",
            merchant="Coffee Shop",
        )
    )

    from uuid import UUID

    tx = await repo.get_by_id(TransactionId(UUID(result.transaction_id)), user_id)
    assert tx is not None
    from decimal import Decimal

    assert tx.amount.amount == Decimal("12.50")
    assert tx.amount.currency.code == "USD"
    assert tx.type_ == TransactionType.EXPENSE
    assert tx.merchant == "Coffee Shop"
    assert tx.notes is None
    assert tx.category_id is None
    assert len(outbox.events) == 1
    assert outbox.events[0].event_type == "TransactionCreated"
    assert outbox.events[0].user_id == user_id.value


async def test_creates_income() -> None:
    uc, repo, _ = _make_use_case()
    user_id = _user_id()

    result = await uc(
        CreateTransactionCommand(
            user_id=user_id,
            raw_amount="1000.00",
            currency="EUR",
            date_=date(2026, 5, 1),
            type_="income",
        )
    )

    from uuid import UUID

    tx = await repo.get_by_id(TransactionId(UUID(result.transaction_id)), user_id)
    assert tx is not None
    assert tx.type_ == TransactionType.INCOME


async def test_raises_on_unknown_currency() -> None:
    uc, _, _ = _make_use_case()

    with pytest.raises(InvalidCurrencyError):
        await uc(
            CreateTransactionCommand(
                user_id=_user_id(),
                raw_amount="10.00",
                currency="XXX",
                date_=date(2026, 5, 1),
                type_="expense",
            )
        )


async def test_raises_on_negative_amount() -> None:
    uc, _, _ = _make_use_case()

    with pytest.raises(InvalidMoneyError):
        await uc(
            CreateTransactionCommand(
                user_id=_user_id(),
                raw_amount="-5.00",
                currency="USD",
                date_=date(2026, 5, 1),
                type_="expense",
            )
        )


async def test_stores_category_id() -> None:
    uc, repo, _ = _make_use_case()
    user_id = _user_id()
    cat_id = str(uuid.uuid4())

    result = await uc(
        CreateTransactionCommand(
            user_id=user_id,
            raw_amount="50.00",
            currency="USD",
            date_=date(2026, 5, 1),
            type_="expense",
            raw_category_id=cat_id,
        )
    )

    from uuid import UUID

    tx = await repo.get_by_id(TransactionId(UUID(result.transaction_id)), user_id)
    assert tx is not None
    assert tx.category_id is not None
    assert str(tx.category_id) == cat_id


async def test_raises_when_category_is_group() -> None:
    import uuid
    from datetime import date

    from app.application.transactions.ports.category_list_reader import CategoryListItem
    from app.domain.exceptions.domain_errors import CategoryIsGroupError
    from tests.fakes.repositories import FakeCategoryListReader

    reader = FakeCategoryListReader()
    group_id = str(uuid.uuid4())
    reader.seed([CategoryListItem(id_=group_id, name="Food & Drink", parent_id=None)])

    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    user_plan_lookup = MagicMock()
    user_plan_lookup.get_plan = AsyncMock(return_value=Plan.FREE)

    class _NoOpQuotaCheck:
        async def check_and_increment(self, *a: object, **kw: object) -> None: ...
        async def refund(self, *a: object, **kw: object) -> None: ...

    uc = CreateTransactionUseCase(
        transaction_repo=repo,
        outbox_repo=outbox,
        id_generator=FakeTransactionIdGenerator(),
        user_plan_lookup=user_plan_lookup,
        category_list_reader=reader,
        quota_check=_NoOpQuotaCheck(),  # type: ignore[arg-type]
    )
    user_id = _user_id()

    with pytest.raises(CategoryIsGroupError):
        await uc(
            CreateTransactionCommand(
                user_id=user_id,
                raw_amount="500",
                currency="JPY",
                date_=date(2026, 5, 1),
                type_="expense",
                raw_category_id=group_id,
            )
        )


async def test_leaf_category_accepted() -> None:
    import uuid
    from datetime import date

    from app.application.transactions.ports.category_list_reader import CategoryListItem
    from tests.fakes.repositories import FakeCategoryListReader

    reader = FakeCategoryListReader()
    group_id = str(uuid.uuid4())
    leaf_id = str(uuid.uuid4())
    reader.seed(
        [
            CategoryListItem(id_=group_id, name="Food & Drink", parent_id=None),
            CategoryListItem(id_=leaf_id, name="Groceries", parent_id=group_id),
        ]
    )

    repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    user_plan_lookup = MagicMock()
    user_plan_lookup.get_plan = AsyncMock(return_value=Plan.FREE)

    class _NoOpQuotaCheck2:
        async def check_and_increment(self, *a: object, **kw: object) -> None: ...
        async def refund(self, *a: object, **kw: object) -> None: ...

    uc = CreateTransactionUseCase(
        transaction_repo=repo,
        outbox_repo=outbox,
        id_generator=FakeTransactionIdGenerator(),
        user_plan_lookup=user_plan_lookup,
        category_list_reader=reader,
        quota_check=_NoOpQuotaCheck2(),  # type: ignore[arg-type]
    )
    user_id = _user_id()

    result = await uc(
        CreateTransactionCommand(
            user_id=user_id,
            raw_amount="500",
            currency="JPY",
            date_=date(2026, 5, 1),
            type_="expense",
            raw_category_id=leaf_id,
        )
    )

    assert result.transaction_id is not None
