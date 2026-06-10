import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.application.common.exceptions import StorageError
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from app.domain.value_objects.money import Currency, Money
from app.outbound.adapters.sqla.search.transaction_reader import SqlaSearchTransactionReader


def _make_tx(tx_id: uuid.UUID, user_id_val: uuid.UUID) -> Transaction:
    return Transaction(
        id_=TransactionId(tx_id),
        user_id=UserId(user_id_val),
        type_=TransactionType.EXPENSE,
        amount=Money(amount=Decimal("10.00"), currency=Currency("USD")),
        date=date(2026, 1, 1),
        merchant="Shop",
        notes=None,
        category_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_get_by_ids_empty_returns_empty_without_query() -> None:
    """get_by_ids([], user_id) returns [] without calling session.execute."""
    session = MagicMock()
    session.execute = AsyncMock()
    user_id = UserId(uuid.uuid4())

    reader = SqlaSearchTransactionReader(session)
    result = await reader.get_by_ids([], user_id)

    assert result == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_by_ids_returns_results_in_input_order() -> None:
    """DB returns [tx_b, tx_a] but input ids order is [id_a, id_b] → result must be [tx_a, tx_b]."""
    user_id = UserId(uuid.uuid4())
    id_a = uuid.uuid4()
    id_b = uuid.uuid4()
    tx_a = _make_tx(id_a, user_id.value)
    tx_b = _make_tx(id_b, user_id.value)

    session = MagicMock()
    mock_result = MagicMock()
    # DB returns them in opposite order
    mock_result.scalars.return_value.all.return_value = [tx_b, tx_a]
    session.execute = AsyncMock(return_value=mock_result)

    reader = SqlaSearchTransactionReader(session)
    result = await reader.get_by_ids([TransactionId(id_a), TransactionId(id_b)], user_id)

    # Result should be in input order: [tx_a, tx_b]
    assert result == [tx_a, tx_b]
    assert result[0].id_.value == id_a
    assert result[1].id_.value == id_b


@pytest.mark.asyncio
async def test_get_by_ids_skips_ids_not_in_db() -> None:
    """DB returns only 1 of 2 requested IDs → result has only that 1."""
    user_id = UserId(uuid.uuid4())
    id_a = uuid.uuid4()
    id_b = uuid.uuid4()
    tx_a = _make_tx(id_a, user_id.value)

    session = MagicMock()
    mock_result = MagicMock()
    # Only tx_a is in DB, tx_b is not
    mock_result.scalars.return_value.all.return_value = [tx_a]
    session.execute = AsyncMock(return_value=mock_result)

    reader = SqlaSearchTransactionReader(session)
    result = await reader.get_by_ids([TransactionId(id_a), TransactionId(id_b)], user_id)

    # Only tx_a should be returned
    assert result == [tx_a]
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_by_ids_raises_storage_error_on_sqla_exception() -> None:
    """session.execute raises SQLAlchemyError → StorageError is raised."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("DB connection failed"))
    user_id = UserId(uuid.uuid4())
    id_a = TransactionId(uuid.uuid4())

    reader = SqlaSearchTransactionReader(session)
    with pytest.raises(StorageError):
        await reader.get_by_ids([id_a], user_id)
