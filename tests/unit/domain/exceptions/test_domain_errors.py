from app.domain.exceptions import (
    DomainError,
    InvalidCurrencyError,
    InvalidEmailError,
    InvalidMoneyError,
    WeakPasswordError,
)


def test_all_errors_are_domain_errors() -> None:
    assert issubclass(InvalidEmailError, DomainError)
    assert issubclass(InvalidCurrencyError, DomainError)
    assert issubclass(InvalidMoneyError, DomainError)
    assert issubclass(WeakPasswordError, DomainError)


def test_invalid_email_message_contains_value() -> None:
    err = InvalidEmailError("bad@@email")
    assert "bad@@email" in str(err)


def test_invalid_currency_message_contains_code() -> None:
    err = InvalidCurrencyError("XYZ")
    assert "XYZ" in str(err)
