from datetime import UTC, datetime

import uuid_utils as uuid

from app.domain.entities.user import User
from app.domain.value_objects.email import Email
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.password import UserPasswordHash


def _make_user() -> User:
    return User(
        id_=UserId(uuid.uuid7()),
        email=Email("test@example.com"),
        password_hash=UserPasswordHash("old_hash"),
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


def test_change_password_updates_hash():
    user = _make_user()
    new_hash = UserPasswordHash("new_hash")
    user.change_password(new_hash)
    assert user.password_hash == new_hash


def test_change_password_returns_none():
    user = _make_user()
    result = user.change_password(UserPasswordHash("x"))
    assert result is None
