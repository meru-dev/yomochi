import hashlib

import pytest

from app.application.users.use_cases.confirm_password_reset import (
    ConfirmPasswordResetCommand,
    ConfirmPasswordResetUseCase,
    InvalidPasswordResetTokenError,
)
from app.application.users.use_cases.create_user import CreateUserCommand, CreateUserUseCase
from app.application.users.use_cases.start_password_reset import (
    StartPasswordResetCommand,
    StartPasswordResetUseCase,
)
from app.domain.value_objects.email import Email
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.password import RawPassword
from tests.fakes.id_generator import FakePasswordResetTokenIdGenerator, FakeUserIdGenerator
from tests.fakes.password_hasher import PlaintextHasher
from tests.fakes.repositories import (
    FakeAuditLog,
    FakeMailer,
    FakePasswordResetTokenStore,
    FakeSessionStore,
    FakeUserRepository,
)


async def _register_and_start_reset(
    repo: FakeUserRepository,
    token_store: FakePasswordResetTokenStore,
    mailer: FakeMailer,
) -> str:
    await CreateUserUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        id_generator=FakeUserIdGenerator(),
        audit_log=FakeAuditLog(),
    )(CreateUserCommand(email="alice@example.com", raw_password="secret123"))

    await StartPasswordResetUseCase(
        user_repo=repo,
        token_store=token_store,
        token_id_generator=FakePasswordResetTokenIdGenerator(),
        mailer=mailer,
        audit_log=FakeAuditLog(),
        password_hasher=PlaintextHasher(),
    )(StartPasswordResetCommand(email="alice@example.com"))

    return mailer.sent[0][1]


async def test_resets_password_and_revokes_sessions() -> None:
    repo = FakeUserRepository()
    token_store = FakePasswordResetTokenStore()
    mailer = FakeMailer()
    session_store = FakeSessionStore()
    audit = FakeAuditLog()

    raw_token = await _register_and_start_reset(repo, token_store, mailer)

    uc = ConfirmPasswordResetUseCase(
        user_repo=repo,
        token_store=token_store,
        password_hasher=PlaintextHasher(),
        session_store=session_store,
        audit_log=audit,
    )
    await uc(ConfirmPasswordResetCommand(token=raw_token, new_password="brandnewpass1"))

    user = await repo.get_by_email(Email("alice@example.com"))
    assert user is not None
    assert await PlaintextHasher().verify(RawPassword("brandnewpass1"), user.password_hash)
    assert len(audit.events) == 1
    assert audit.events[0].event_type == AuditEventType.PASSWORD_RESET_CONFIRMED


async def test_raises_on_invalid_token() -> None:
    uc = ConfirmPasswordResetUseCase(
        user_repo=FakeUserRepository(),
        token_store=FakePasswordResetTokenStore(),
        password_hasher=PlaintextHasher(),
        session_store=FakeSessionStore(),
        audit_log=FakeAuditLog(),
    )
    with pytest.raises(InvalidPasswordResetTokenError):
        await uc(ConfirmPasswordResetCommand(token="bogustoken", new_password="newpassword1"))


async def test_token_is_invalidated_after_use() -> None:
    repo = FakeUserRepository()
    token_store = FakePasswordResetTokenStore()
    mailer = FakeMailer()

    raw_token = await _register_and_start_reset(repo, token_store, mailer)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    uc = ConfirmPasswordResetUseCase(
        user_repo=repo,
        token_store=token_store,
        password_hasher=PlaintextHasher(),
        session_store=FakeSessionStore(),
        audit_log=FakeAuditLog(),
    )
    await uc(ConfirmPasswordResetCommand(token=raw_token, new_password="brandnewpass1"))

    assert await token_store.get_valid(token_hash) is None
