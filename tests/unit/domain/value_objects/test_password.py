import pytest

from app.domain.exceptions import WeakPasswordError
from app.domain.value_objects import RawPassword, UserPasswordHash


class TestRawPassword:
    def test_accepts_valid_password(self) -> None:
        p = RawPassword("securepassword123")

        assert p.value == "securepassword123"

    def test_rejects_too_short(self) -> None:
        with pytest.raises(WeakPasswordError):
            RawPassword("short")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(WeakPasswordError):
            RawPassword("x" * 73)

    def test_repr_hides_value(self) -> None:
        p = RawPassword("mysecretpassword")

        assert "mysecretpassword" not in repr(p)
        assert repr(p) == "RawPassword(***)"

    def test_str_hides_value(self) -> None:
        p = RawPassword("mysecretpassword")

        assert str(p) == "***"

    def test_accepts_72_char_password(self) -> None:
        RawPassword("a" * 72)

    def test_accepts_8_char_password(self) -> None:
        RawPassword("a" * 8)


class TestUserPasswordHash:
    def test_stores_hash_string(self) -> None:
        h = UserPasswordHash("$2b$12$fakehash")

        assert h.value == "$2b$12$fakehash"

    def test_str_returns_value(self) -> None:
        assert str(UserPasswordHash("$2b$12$fakehash")) == "$2b$12$fakehash"

    def test_equality_by_value(self) -> None:
        assert UserPasswordHash("hash1") == UserPasswordHash("hash1")
        assert UserPasswordHash("hash1") != UserPasswordHash("hash2")
