from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.outbound.adapters.openai.transaction_text_parser import (
    OpenAITransactionTextParser,
    _ParsedTransaction,
)


def _make_adapter() -> OpenAITransactionTextParser:
    return OpenAITransactionTextParser(
        gateway=MagicMock(),
        model="gpt-4o-mini",
        read_timeout_seconds=30.0,
    )


def _make_parsed(**kwargs: object) -> _ParsedTransaction:
    defaults: dict[str, object] = {
        "amount": "3500",
        "currency": "JPY",
        "merchant": "Lawson",
        "transaction_type": "expense",
        "date_hint": "2026-05-20",
        "suggested_category_name": "Food",
        "confidence": 0.95,
        "low_confidence_fields": [],
    }
    defaults.update(kwargs)
    return _ParsedTransaction(**defaults)  # type: ignore[arg-type]


def test_maps_all_fields_to_draft() -> None:
    adapter = _make_adapter()
    categories = [("cat-1", "Food"), ("cat-2", "Transport")]
    parsed = _make_parsed()

    draft = adapter._to_draft(parsed, categories)

    assert draft.amount == "3500"
    assert draft.currency == "JPY"
    assert draft.merchant == "Lawson"
    assert draft.transaction_type == "expense"
    assert draft.date == date(2026, 5, 20)
    assert draft.suggested_category_id == "cat-1"
    assert draft.confidence == 0.95
    assert draft.requires_review is False
    assert draft.low_confidence_fields == ()


def test_category_match_is_case_insensitive() -> None:
    adapter = _make_adapter()
    categories = [("cat-1", "food & drink")]
    parsed = _make_parsed(suggested_category_name="Food & Drink")

    draft = adapter._to_draft(parsed, categories)

    assert draft.suggested_category_id == "cat-1"


def test_unmatched_category_returns_none() -> None:
    adapter = _make_adapter()
    parsed = _make_parsed(suggested_category_name="Unknown Category")

    draft = adapter._to_draft(parsed, [("cat-1", "Food")])

    assert draft.suggested_category_id is None


def test_requires_review_on_low_confidence() -> None:
    adapter = _make_adapter()
    parsed = _make_parsed(confidence=0.5)

    draft = adapter._to_draft(parsed, [])

    assert draft.requires_review is True


def test_requires_review_when_amount_missing() -> None:
    adapter = _make_adapter()
    parsed = _make_parsed(amount=None, confidence=0.9)

    draft = adapter._to_draft(parsed, [])

    assert draft.requires_review is True


def test_requires_review_when_currency_missing() -> None:
    adapter = _make_adapter()
    parsed = _make_parsed(currency=None, confidence=0.9)

    draft = adapter._to_draft(parsed, [])

    assert draft.requires_review is True


def test_requires_review_when_type_missing() -> None:
    adapter = _make_adapter()
    parsed = _make_parsed(transaction_type=None, confidence=0.9)

    draft = adapter._to_draft(parsed, [])

    assert draft.requires_review is True


def test_invalid_date_hint_returns_none_date() -> None:
    adapter = _make_adapter()
    parsed = _make_parsed(date_hint="not-a-date")

    draft = adapter._to_draft(parsed, [])

    assert draft.date is None


def test_null_date_hint_returns_none_date() -> None:
    adapter = _make_adapter()
    parsed = _make_parsed(date_hint=None)

    draft = adapter._to_draft(parsed, [])

    assert draft.date is None


def test_no_categories_returns_null_suggestion() -> None:
    adapter = _make_adapter()
    parsed = _make_parsed(suggested_category_name=None)

    draft = adapter._to_draft(parsed, [])

    assert draft.suggested_category_id is None
