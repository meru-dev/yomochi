from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.domain.exceptions.domain_errors import InvalidCurrencyError, InvalidMoneyError

# ISO 4217 currency code → minor unit digits.
# Subset covering major world currencies; extend when new currencies are needed.
_ISO_4217: dict[str, int] = {
    # 0 fractional digits
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "IDR": 0,
    "CLP": 0,
    "ISK": 0,
    "UGX": 0,
    "RWF": 0,
    "GNF": 0,
    "PYG": 0,
    # 2 fractional digits (the vast majority)
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CHF": 2,
    "CAD": 2,
    "AUD": 2,
    "NZD": 2,
    "CNY": 2,
    "HKD": 2,
    "TWD": 2,
    "SGD": 2,
    "MYR": 2,
    "PHP": 2,
    "THB": 2,
    "INR": 2,
    "PKR": 2,
    "BDT": 2,
    "LKR": 2,
    "NPR": 2,
    "SEK": 2,
    "NOK": 2,
    "DKK": 2,
    "PLN": 2,
    "CZK": 2,
    "HUF": 2,
    "RON": 2,
    "BGN": 2,
    "HRK": 2,
    "RSD": 2,
    "UAH": 2,
    "RUB": 2,
    "TRY": 2,
    "MXN": 2,
    "BRL": 2,
    "ARS": 2,
    "COP": 2,
    "PEN": 2,
    "VEF": 2,
    "ZAR": 2,
    "EGP": 2,
    "NGN": 2,
    "KES": 2,
    "GHS": 2,
    "MAD": 2,
    "SAR": 2,
    "AED": 2,
    "QAR": 2,
    "ILS": 2,
    "GEL": 2,
    "AMD": 2,
    "AZN": 2,
    "KZT": 2,
    "UZS": 2,
    "MNT": 2,
    # 3 fractional digits
    "KWD": 3,
    "BHD": 3,
    "OMR": 3,
    "JOD": 3,
    "IQD": 3,
    "TND": 3,
    "LYD": 3,
}


@dataclass(frozen=True, slots=True)
class Currency:
    code: str
    minor_unit_digits: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        normalized = self.code.strip().upper()
        object.__setattr__(self, "code", normalized)
        if normalized not in _ISO_4217:
            raise InvalidCurrencyError(normalized)
        object.__setattr__(self, "minor_unit_digits", _ISO_4217[normalized])

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not self.amount.is_finite():
            raise InvalidMoneyError("Money amount must be a finite decimal")
        if self.amount < Decimal(0):
            raise InvalidMoneyError("Money amount cannot be negative")
        # normalize() strips trailing zeros so Decimal('320000.0000') → Decimal('3.2E+5'),
        # giving exponent ≥ 0 (actual_places = 0) rather than -4 for JPY validation.
        _sign, _digits, exponent = self.amount.normalize().as_tuple()
        if not isinstance(exponent, int):
            raise InvalidMoneyError(
                f"Decimal exponent must be an int, got {type(exponent).__name__!r}; "
                "value is likely NaN or Infinity (should have been caught above)"
            )
        actual_places = -exponent if exponent < 0 else 0
        if actual_places > self.currency.minor_unit_digits:
            raise InvalidMoneyError(
                f"Amount {self.amount!r} has {actual_places} decimal places "
                f"but {self.currency.code} allows at most "
                f"{self.currency.minor_unit_digits}"
            )

    def __composite_values__(self) -> tuple[Decimal, str]:
        return self.amount, self.currency.code

    @classmethod
    def from_string(cls, raw_amount: str, currency: Currency) -> "Money":
        """Parse a user-supplied amount string into Money.

        Raises `InvalidMoneyError` for non-numeric input, negative values, or
        precision exceeding the currency's minor-unit digits.
        """
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation as exc:
            raise InvalidMoneyError("Amount must be a valid number") from exc
        return cls(amount=amount, currency=currency)
