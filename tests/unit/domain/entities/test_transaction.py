from datetime import UTC, date, datetime
from decimal import Decimal

import uuid_utils as uuid

from app.domain.entities.transaction import Transaction
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from app.domain.value_objects.money import Currency, Money


def _make_transaction(**kwargs) -> Transaction:
    defaults = {
        "id_": TransactionId(uuid.uuid7()),
        "user_id": UserId(uuid.uuid7()),
        "amount": Money(amount=Decimal("10.00"), currency=Currency("USD")),
        "date": date(2025, 1, 15),
        "type_": TransactionType.EXPENSE,
        "merchant": "Coffee Shop",
        "notes": None,
        "category_id": None,
        "created_at": datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return Transaction(**defaults)


def test_apply_update_changes_amount():
    tx = _make_transaction()
    new_money = Money(amount=Decimal("20.00"), currency=Currency("EUR"))
    tx.apply_update(amount=new_money)
    assert tx.amount == new_money


def test_apply_update_skips_none_fields():
    tx = _make_transaction()
    original_amount = tx.amount
    tx.apply_update(date=date(2025, 3, 1))
    assert tx.amount == original_amount
    assert tx.date == date(2025, 3, 1)


def test_apply_update_sets_updated_at():
    tx = _make_transaction()
    assert tx.updated_at is None
    tx.apply_update(merchant="New Shop")
    assert tx.updated_at is not None


def test_apply_update_with_no_fields_is_noop():
    tx = _make_transaction()
    tx.apply_update()
    assert tx.updated_at is None  # nothing changed, no timestamp set
