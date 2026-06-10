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
from app.outbound.adapters.sqla.search.transaction_searcher import (
    SqlaTransactionSearcher,
    _escape_like,
)


def _make_tx(merchant: str | None = "Starbucks") -> Transaction:
    return Transaction(
        id_=TransactionId(uuid.uuid4()),
        user_id=UserId(uuid.uuid4()),
        type_=TransactionType.EXPENSE,
        amount=Money(amount=Decimal("5.00"), currency=Currency("USD")),
        date=date(2026, 1, 1),
        merchant=merchant,
        notes=None,
        category_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_search_returns_scalars_from_session() -> None:
    tx = _make_tx()
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [tx]
    session.execute = AsyncMock(return_value=mock_result)

    searcher = SqlaTransactionSearcher(session)
    result = await searcher.search(tx.user_id, "star", limit=10)

    assert result == [tx]
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_search_returns_empty_list_on_no_match() -> None:
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    searcher = SqlaTransactionSearcher(session)
    result = await searcher.search(UserId(uuid.uuid4()), "xyz", limit=10)

    assert result == []


def test_escape_like_escapes_percent_and_underscore() -> None:
    """_escape_like must escape %, _, and backslash for safe SQL LIKE patterns."""
    assert _escape_like("50%_off") == "50\\%\\_off"
    assert _escape_like("back\\slash") == "back\\\\slash"
    assert _escape_like("normal") == "normal"
    assert _escape_like("") == ""


@pytest.mark.asyncio
async def test_search_escapes_sql_wildcards() -> None:
    """User query containing % or _ must not act as SQL wildcards."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    searcher = SqlaTransactionSearcher(session)
    # Should not raise, should call session.execute with escaped query
    result = await searcher.search(UserId(uuid.uuid4()), "50%_off", limit=10)

    assert result == []
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_search_raises_storage_error_on_sqla_exception() -> None:
    """StorageError is raised when SQLAlchemyError occurs."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=SQLAlchemyError("DB down"))

    searcher = SqlaTransactionSearcher(session)
    with pytest.raises(StorageError):
        await searcher.search(UserId(uuid.uuid4()), "test", limit=10)
