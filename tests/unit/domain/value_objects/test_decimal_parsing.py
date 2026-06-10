from decimal import Decimal, InvalidOperation

import pytest

from app.domain.exceptions.domain_errors import InvalidMoneyError


def _safe_decimal(raw: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise InvalidMoneyError("Amount must be a valid number") from exc


def test_valid_amount_parses():
    assert _safe_decimal("42.50") == Decimal("42.50")


def test_text_amount_raises_invalid_money_error():
    with pytest.raises(InvalidMoneyError, match="Amount must be a valid number"):
        _safe_decimal("fifty")


def test_empty_amount_raises_invalid_money_error():
    with pytest.raises(InvalidMoneyError):
        _safe_decimal("")


def test_expression_amount_raises_invalid_money_error():
    with pytest.raises(InvalidMoneyError):
        _safe_decimal("1+1")
