import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application.users.session import Session
from app.application.users.use_cases.change_password import (
    ChangePasswordCommand,
    ChangePasswordUseCase,
    InvalidCurrentPasswordError,
    UserNotFoundError,
)
from app.application.users.use_cases.create_user import CreateUserCommand, CreateUserUseCase
from app.domain.value_objects.email import Email
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.password import RawPassword
from tests.fakes.id_generator import FakeSessionIdGenerator, FakeUserIdGenerator
from tests.fakes.password_hasher import PlaintextHasher
from tests.fakes.repositories import FakeAuditLog, FakeSessionStore, FakeUserRepository


def _make_uc(repo: FakeUserRepository, audit: FakeAuditLog) -> ChangePasswordUseCase:
    return ChangePasswordUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        session_store=FakeSessionStore(),
        audit_log=audit,
    )


async def _register(repo: FakeUserRepository) -> None:
    await CreateUserUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        id_generator=FakeUserIdGenerator(),
        audit_log=FakeAuditLog(),
    )(CreateUserCommand(email="alice@example.com", raw_password="secret123"))


async def test_changes_password_and_records_audit() -> None:
    repo = FakeUserRepository()
    await _register(repo)
    user = await repo.get_by_email(Email("alice@example.com"))
    assert user is not None

    audit = FakeAuditLog()
    uc = _make_uc(repo, audit)
    await uc(
        ChangePasswordCommand(
            user_id=user.id_,
            current_password="secret123",
            new_password="newpassword456",
        )
    )

    updated = await repo.get_by_id(user.id_)
    assert updated is not None
    assert await PlaintextHasher().verify(RawPassword("newpassword456"), updated.password_hash)
    assert len(audit.events) == 1
    assert audit.events[0].event_type == AuditEventType.PASSWORD_CHANGED


async def test_raises_on_wrong_current_password() -> None:
    repo = FakeUserRepository()
    await _register(repo)
    user = await repo.get_by_email(Email("alice@example.com"))
    assert user is not None

    with pytest.raises(InvalidCurrentPasswordError):
        await _make_uc(repo, FakeAuditLog())(
            ChangePasswordCommand(
                user_id=user.id_,
                current_password="wrongpassword1",
                new_password="newpassword456",
            )
        )


async def test_raises_if_user_not_found() -> None:
    with pytest.raises(UserNotFoundError):
        await _make_uc(FakeUserRepository(), FakeAuditLog())(
            ChangePasswordCommand(
                user_id=UserId(uuid.uuid4()),
                current_password="secret123",
                new_password="newpassword456",
            )
        )


async def test_revokes_all_sessions_on_password_change() -> None:
    repo = FakeUserRepository()
    await _register(repo)
    user = await repo.get_by_email(Email("alice@example.com"))
    assert user is not None

    session_store = FakeSessionStore()
    session = Session(
        id_=FakeSessionIdGenerator()(),
        user_id=user.id_,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_agent="agent",
        ip="127.0.0.1",
    )
    await session_store.save(session)

    await ChangePasswordUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        session_store=session_store,
        audit_log=FakeAuditLog(),
    )(
        ChangePasswordCommand(
            user_id=user.id_,
            current_password="secret123",
            new_password="newpassword456",
        )
    )

    assert await session_store.list_active(user.id_) == []
