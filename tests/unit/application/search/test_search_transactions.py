import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.application.search.use_cases.search_transactions import SearchTransactionsUseCase
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from app.domain.value_objects.money import Currency, Money

pytestmark = pytest.mark.asyncio


def _make_tx(tx_id: uuid.UUID, user_id: UserId) -> Transaction:
    return Transaction(
        id_=TransactionId(tx_id),
        user_id=user_id,
        type_=TransactionType.EXPENSE,
        amount=Money(amount=Decimal("50.00"), currency=Currency("USD")),
        date=date(2026, 4, 1),
        merchant="Cafe",
        notes=None,
        category_id=None,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
        updated_at=None,
    )


def _make_uc(
    cached_ids: list[uuid.UUID] | None = None,
    search_results: list[Transaction] | None = None,
    hydrated: list[Transaction] | None = None,
) -> tuple[SearchTransactionsUseCase, AsyncMock, AsyncMock, AsyncMock]:
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=cached_ids)
    cache.set = AsyncMock()

    searcher = AsyncMock()
    searcher.search = AsyncMock(return_value=search_results or [])

    tx_reader = AsyncMock()
    tx_reader.get_by_ids = AsyncMock(return_value=hydrated or [])

    uc = SearchTransactionsUseCase(cache=cache, searcher=searcher, tx_reader=tx_reader)
    return uc, cache, searcher, tx_reader


async def test_returns_cached_results_without_calling_searcher() -> None:
    user_id = UserId(uuid.uuid4())
    tx_id = uuid.uuid4()
    tx = _make_tx(tx_id, user_id)

    uc, _cache, searcher, tx_reader = _make_uc(
        cached_ids=[tx_id],
        hydrated=[tx],
    )

    result = await uc(user_id=user_id, query="cafe", limit=10)

    assert result == [tx]
    searcher.search.assert_not_called()
    tx_reader.get_by_ids.assert_called_once()


async def test_calls_searcher_on_cache_miss() -> None:
    user_id = UserId(uuid.uuid4())
    tx_id = uuid.uuid4()
    tx = _make_tx(tx_id, user_id)

    uc, _cache, searcher, _tx_reader = _make_uc(
        cached_ids=None,
        search_results=[tx],
    )

    result = await uc(user_id=user_id, query="cafe", limit=10)

    searcher.search.assert_called_once_with(user_id, "cafe", 10)
    assert result == [tx]


async def test_caches_results_after_search() -> None:
    user_id = UserId(uuid.uuid4())
    tx_id = uuid.uuid4()
    tx = _make_tx(tx_id, user_id)

    uc, cache, _searcher, _tx_reader = _make_uc(
        cached_ids=None,
        search_results=[tx],
    )

    await uc(user_id=user_id, query="cafe", limit=10)

    cache.set.assert_called_once_with(user_id, "cafe", [tx_id])


async def test_returns_empty_when_no_results() -> None:
    user_id = UserId(uuid.uuid4())
    uc, cache, _, _ = _make_uc(cached_ids=None, search_results=[])

    result = await uc(user_id=user_id, query="xyz", limit=10)

    assert result == []
    cache.set.assert_called_once_with(user_id, "xyz", [])


async def test_cache_hit_applies_limit() -> None:
    """Cache hit with 5 stored IDs and limit=3 must only fetch 3 IDs from tx_reader."""
    user_id = UserId(uuid.uuid4())
    stored_ids = [uuid.uuid4() for _ in range(5)]
    hydrated = [_make_tx(stored_ids[i], user_id) for i in range(3)]

    uc, _, _, tx_reader = _make_uc(
        cached_ids=stored_ids,
        hydrated=hydrated,
    )

    result = await uc(user_id=user_id, query="coffee", limit=3)

    # tx_reader must receive only 3 ids, not all 5
    called_ids = tx_reader.get_by_ids.call_args[0][0]
    assert len(called_ids) == 3
    assert result == hydrated
