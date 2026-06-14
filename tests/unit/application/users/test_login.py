from datetime import timedelta

import pytest

from app.application.users.use_cases.create_user import CreateUserCommand, CreateUserUseCase
from app.application.users.use_cases.login import (
    InvalidCredentialsError,
    LoginCommand,
    LoginUseCase,
)
from app.domain.value_objects.enums import AuditEventType
from tests.fakes.id_generator import FakeSessionIdGenerator, FakeUserIdGenerator
from tests.fakes.password_hasher import PlaintextHasher, SpyHasher
from tests.fakes.repositories import FakeAuditLog, FakeSessionStore, FakeUserRepository

_TTL = timedelta(days=30)
_CMD = LoginCommand(
    email="alice@example.com",
    raw_password="secret123",
    user_agent="test-agent",
    ip="127.0.0.1",
)


def _make_login_uc(repo: FakeUserRepository, audit: FakeAuditLog) -> LoginUseCase:
    return LoginUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        session_store=FakeSessionStore(),
        session_id_generator=FakeSessionIdGenerator(),
        audit_log=audit,
        session_ttl=_TTL,
    )


async def _register(repo: FakeUserRepository) -> None:
    await CreateUserUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        id_generator=FakeUserIdGenerator(),
        audit_log=FakeAuditLog(),
    )(CreateUserCommand(email="alice@example.com", raw_password="secret123"))


async def test_login_returns_session() -> None:
    repo = FakeUserRepository()
    await _register(repo)
    audit = FakeAuditLog()
    uc = _make_login_uc(repo, audit)

    result = await uc(_CMD)

    assert result.session.user_agent == "test-agent"
    assert result.session.ip == "127.0.0.1"
    assert len(audit.events) == 1
    assert audit.events[0].event_type == AuditEventType.USER_LOGIN


async def test_login_fails_with_wrong_password() -> None:
    repo = FakeUserRepository()
    await _register(repo)
    uc = _make_login_uc(repo, FakeAuditLog())

    wrong = LoginCommand(
        email="alice@example.com", raw_password="wrongpass1", user_agent="a", ip="1"
    )
    with pytest.raises(InvalidCredentialsError):
        await uc(wrong)


async def test_login_fails_with_unknown_email() -> None:
    uc = _make_login_uc(FakeUserRepository(), FakeAuditLog())

    with pytest.raises(InvalidCredentialsError):
        await uc(_CMD)


async def test_login_unknown_email_still_calls_verify() -> None:
    """Hasher.verify must be called even when user is not found (timing-oracle fix)."""
    spy = SpyHasher()
    uc = LoginUseCase(
        user_repo=FakeUserRepository(),
        password_hasher=spy,
        session_store=FakeSessionStore(),
        session_id_generator=FakeSessionIdGenerator(),
        audit_log=FakeAuditLog(),
        session_ttl=_TTL,
    )

    with pytest.raises(InvalidCredentialsError):
        await uc(_CMD)

    assert spy.verify_call_count == 1


async def test_session_is_persisted() -> None:
    repo = FakeUserRepository()
    await _register(repo)
    session_store = FakeSessionStore()
    uc = LoginUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        session_store=session_store,
        session_id_generator=FakeSessionIdGenerator(),
        audit_log=FakeAuditLog(),
        session_ttl=_TTL,
    )

    result = await uc(_CMD)

    sessions = await session_store.list_active(result.session.user_id)
    assert len(sessions) == 1
    assert sessions[0].id_ == result.session.id_
