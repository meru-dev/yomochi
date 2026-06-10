import uuid
from datetime import UTC, datetime

from app.domain.entities import User
from app.domain.value_objects import Email, Plan, UserId, UserPasswordHash


def _make_user(user_id: uuid.UUID | None = None) -> User:
    return User(
        id_=UserId(user_id or uuid.uuid4()),
        email=Email("user@example.com"),
        password_hash=UserPasswordHash("$2b$12$fakehash"),
        created_at=datetime.now(UTC),
    )


def test_default_plan_is_free() -> None:
    user = _make_user()

    assert user.plan == Plan.FREE


def test_equality_by_id() -> None:
    uid = uuid.uuid4()
    user_a = _make_user(uid)
    user_b = _make_user(uid)

    assert user_a == user_b


def test_inequality_for_different_ids() -> None:
    assert _make_user() != _make_user()


def test_users_with_same_id_have_same_hash() -> None:
    uid = uuid.uuid4()
    assert hash(_make_user(uid)) == hash(_make_user(uid))


def test_user_not_equal_to_non_user() -> None:
    assert _make_user().__eq__("not a user") is NotImplemented


def test_email_is_normalised() -> None:
    user = User(
        id_=UserId(uuid.uuid4()),
        email=Email("ADMIN@EXAMPLE.COM"),
        password_hash=UserPasswordHash("$2b$12$fakehash"),
        created_at=datetime.now(UTC),
    )

    assert user.email.value == "admin@example.com"
