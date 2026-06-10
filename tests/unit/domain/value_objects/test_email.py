import pytest

from app.domain.exceptions import InvalidEmailError
from app.domain.value_objects import Email


def test_normalises_to_lowercase() -> None:
    email = Email("User@Example.COM")

    assert email.value == "user@example.com"


def test_strips_whitespace() -> None:
    email = Email("  user@example.com  ")

    assert email.value == "user@example.com"


def test_equality_is_case_insensitive() -> None:
    assert Email("User@Example.com") == Email("user@example.com")


@pytest.mark.parametrize(
    "bad",
    [
        "notanemail",
        "@nodomain",
        "no-at-sign",
        "missing@tld",
        "spaces in@email.com",
        "",
    ],
)
def test_rejects_invalid_format(bad: str) -> None:
    with pytest.raises(InvalidEmailError):
        Email(bad)


def test_str_returns_value() -> None:
    assert str(Email("user@example.com")) == "user@example.com"


def test_email_repr_does_not_expose_value() -> None:
    email = Email("Alice@Example.com")
    assert "Alice" not in repr(email)
    assert "example.com" not in repr(email)
    assert "Email" in repr(email)
