from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.transactions.ports.category_list_reader import CategoryListItem
from app.application.transactions.use_cases.parse_transaction_text import (
    DraftTransaction,
    ParseTransactionTextQuery,
    ParseTransactionTextUseCase,
)
from app.domain.exceptions.domain_errors import InvalidTransactionTextError
from app.domain.value_objects.ids import UserId

pytestmark = pytest.mark.asyncio

_USER_ID = UserId(uuid.uuid4())


def _make_draft(**kwargs: object) -> DraftTransaction:
    defaults: dict[str, object] = {
        "amount": "3500",
        "currency": "JPY",
        "merchant": "Lawson",
        "transaction_type": "expense",
        "date": date(2026, 5, 21),
        "suggested_category_id": None,
        "confidence": 0.95,
        "requires_review": False,
        "low_confidence_fields": (),
    }
    defaults.update(kwargs)
    return DraftTransaction(**defaults)  # type: ignore[arg-type]


def _make_use_case(draft: DraftTransaction) -> ParseTransactionTextUseCase:
    category_list_reader = MagicMock()
    category_list_reader.list_for_user = AsyncMock(return_value=[])
    parser = MagicMock()
    parser.parse = AsyncMock(return_value=draft)
    return ParseTransactionTextUseCase(
        category_list_reader=category_list_reader, text_parser=parser
    )


async def test_returns_draft_from_parser() -> None:
    draft = _make_draft()
    uc = _make_use_case(draft)
    result = await uc(ParseTransactionTextQuery(user_id=_USER_ID, text="spent 3500 at Lawson"))
    assert result.draft == draft


async def test_raises_on_empty_text() -> None:
    uc = _make_use_case(_make_draft())
    with pytest.raises(InvalidTransactionTextError):
        await uc(ParseTransactionTextQuery(user_id=_USER_ID, text=""))


async def test_raises_on_whitespace_only() -> None:
    uc = _make_use_case(_make_draft())
    with pytest.raises(InvalidTransactionTextError):
        await uc(ParseTransactionTextQuery(user_id=_USER_ID, text="   "))


async def test_raises_on_text_too_long() -> None:
    uc = _make_use_case(_make_draft())
    with pytest.raises(InvalidTransactionTextError):
        await uc(ParseTransactionTextQuery(user_id=_USER_ID, text="x" * 501))


async def test_exactly_500_chars_is_valid() -> None:
    draft = _make_draft()
    uc = _make_use_case(draft)
    result = await uc(ParseTransactionTextQuery(user_id=_USER_ID, text="x" * 500))
    assert result.draft == draft


async def test_strips_whitespace_before_empty_check() -> None:
    draft = _make_draft()
    uc = _make_use_case(draft)
    result = await uc(ParseTransactionTextQuery(user_id=_USER_ID, text="  Lawson 3500  "))
    assert result.draft == draft


async def test_passes_categories_to_parser() -> None:
    cat_id = uuid.uuid4()
    item = CategoryListItem(id_=str(cat_id), name="Food", parent_id="group-1")

    category_list_reader = MagicMock()
    category_list_reader.list_for_user = AsyncMock(return_value=[item])
    parser = MagicMock()
    parser.parse = AsyncMock(return_value=_make_draft())
    uc = ParseTransactionTextUseCase(category_list_reader=category_list_reader, text_parser=parser)

    await uc(ParseTransactionTextQuery(user_id=_USER_ID, text="bought food"))

    parser.parse.assert_awaited_once()
    call_args = parser.parse.call_args
    categories_arg = call_args.args[1]
    assert categories_arg == [(str(cat_id), "Food")]


async def test_parse_text_sends_only_leaf_categories_to_parser() -> None:
    group_item = CategoryListItem(id_="group-1", name="Food & Drink", parent_id=None)
    leaf_item = CategoryListItem(id_="leaf-1", name="Groceries", parent_id="group-1")

    reader = MagicMock()
    reader.list_for_user = AsyncMock(return_value=[group_item, leaf_item])

    captured: list[list] = []

    async def fake_parse(text, categories, today):
        captured.append(list(categories))
        return DraftTransaction(
            amount="100",
            currency="JPY",
            merchant=None,
            transaction_type="expense",
            date=None,
            suggested_category_id=None,
            confidence=0.9,
            requires_review=False,
            low_confidence_fields=(),
        )

    parser = MagicMock()
    parser.parse = fake_parse

    uc = ParseTransactionTextUseCase(category_list_reader=reader, text_parser=parser)
    await uc(ParseTransactionTextQuery(user_id=_USER_ID, text="coffee 500 yen"))

    assert len(captured) == 1
    assert len(captured[0]) == 1, f"Expected 1 leaf, got {len(captured[0])}: {captured[0]}"
    assert captured[0][0] == ("leaf-1", "Groceries")
