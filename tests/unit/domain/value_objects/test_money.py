from decimal import Decimal

import pytest

from app.domain.exceptions import InvalidCurrencyError, InvalidMoneyError
from app.domain.value_objects import Currency, Money


class TestCurrency:
    def test_normalises_code_to_uppercase(self) -> None:
        assert Currency("usd").code == "USD"

    def test_strips_whitespace(self) -> None:
        assert Currency(" EUR ").code == "EUR"

    def test_populates_minor_unit_digits(self) -> None:
        assert Currency("USD").minor_unit_digits == 2
        assert Currency("JPY").minor_unit_digits == 0
        assert Currency("KWD").minor_unit_digits == 3

    def test_rejects_unknown_code(self) -> None:
        with pytest.raises(InvalidCurrencyError):
            Currency("XYZ")

    def test_str_returns_code(self) -> None:
        assert str(Currency("EUR")) == "EUR"

    def test_equality_by_value(self) -> None:
        assert Currency("USD") == Currency("usd")


class TestMoney:
    def test_valid_usd(self) -> None:
        m = Money(Decimal("10.50"), Currency("USD"))

        assert m.amount == Decimal("10.50")
        assert m.currency.code == "USD"

    def test_valid_jpy_no_decimals(self) -> None:
        m = Money(Decimal("1000"), Currency("JPY"))

        assert m.amount == Decimal("1000")

    def test_valid_kwd_three_decimals(self) -> None:
        m = Money(Decimal("1.234"), Currency("KWD"))

        assert m.amount == Decimal("1.234")

    def test_valid_fewer_decimals_than_allowed(self) -> None:
        m = Money(Decimal("10.5"), Currency("USD"))

        assert m.amount == Decimal("10.5")

    def test_rejects_negative_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("-1.00"), Currency("USD"))

    def test_rejects_too_many_decimals_usd(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("10.555"), Currency("USD"))

    def test_rejects_any_decimals_for_jpy(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("100.50"), Currency("JPY"))

    def test_rejects_four_decimals_for_kwd(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1.2345"), Currency("KWD"))

    def test_zero_is_valid(self) -> None:
        m = Money(Decimal("0"), Currency("EUR"))

        assert m.amount == Decimal("0")

    def test_equality_by_value(self) -> None:
        usd = Currency("USD")
        assert Money(Decimal("10.00"), usd) == Money(Decimal("10.00"), usd)
        assert Money(Decimal("10.00"), usd) != Money(Decimal("9.99"), usd)
