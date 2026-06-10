import pytest

from app.application.users.use_cases.create_user import (
    CreateUserCommand,
    CreateUserUseCase,
    UserAlreadyExistsError,
)
from app.domain.exceptions.domain_errors import InvalidEmailError, WeakPasswordError
from app.domain.value_objects.enums import AuditEventType
from tests.fakes.id_generator import FakeUserIdGenerator
from tests.fakes.password_hasher import PlaintextHasher
from tests.fakes.repositories import FakeAuditLog, FakeUserRepository


def _make_use_case() -> tuple[CreateUserUseCase, FakeUserRepository, FakeAuditLog]:
    repo = FakeUserRepository()
    audit = FakeAuditLog()
    uc = CreateUserUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        id_generator=FakeUserIdGenerator(),
        audit_log=audit,
    )
    return uc, repo, audit


async def test_creates_user_and_records_audit() -> None:
    uc, repo, audit = _make_use_case()

    result = await uc(CreateUserCommand(email="alice@example.com", raw_password="secret123"))

    user = await repo.get_by_id(result.user_id)
    assert user is not None
    assert str(user.email) == "alice@example.com"
    assert len(audit.events) == 1
    assert audit.events[0].event_type == AuditEventType.USER_REGISTERED
    assert audit.events[0].user_id == result.user_id


async def test_email_is_normalised_to_lowercase() -> None:
    uc, repo, _ = _make_use_case()

    result = await uc(CreateUserCommand(email="Alice@Example.COM", raw_password="secret123"))

    user = await repo.get_by_id(result.user_id)
    assert user is not None
    assert str(user.email) == "alice@example.com"


async def test_raises_if_email_already_exists() -> None:
    uc, _, _ = _make_use_case()
    cmd = CreateUserCommand(email="alice@example.com", raw_password="secret123")
    await uc(cmd)

    with pytest.raises(UserAlreadyExistsError):
        await uc(cmd)


async def test_raises_on_invalid_email() -> None:
    uc, _, _ = _make_use_case()

    with pytest.raises(InvalidEmailError):
        await uc(CreateUserCommand(email="not-an-email", raw_password="secret123"))


async def test_raises_on_weak_password() -> None:
    uc, _, _ = _make_use_case()

    with pytest.raises(WeakPasswordError):
        await uc(CreateUserCommand(email="alice@example.com", raw_password="short"))
