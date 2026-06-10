from app.application.users.use_cases.create_user import CreateUserCommand, CreateUserUseCase
from app.application.users.use_cases.start_password_reset import (
    StartPasswordResetCommand,
    StartPasswordResetUseCase,
)
from app.domain.value_objects.enums import AuditEventType
from tests.fakes.id_generator import FakePasswordResetTokenIdGenerator, FakeUserIdGenerator
from tests.fakes.password_hasher import PlaintextHasher
from tests.fakes.repositories import (
    FakeAuditLog,
    FakeMailer,
    FakePasswordResetTokenStore,
    FakeUserRepository,
)


def _make_uc(
    repo: FakeUserRepository,
    token_store: FakePasswordResetTokenStore,
    mailer: FakeMailer,
    audit: FakeAuditLog,
) -> StartPasswordResetUseCase:
    return StartPasswordResetUseCase(
        user_repo=repo,
        token_store=token_store,
        token_id_generator=FakePasswordResetTokenIdGenerator(),
        mailer=mailer,
        audit_log=audit,
    )


async def _register(repo: FakeUserRepository) -> None:
    await CreateUserUseCase(
        user_repo=repo,
        password_hasher=PlaintextHasher(),
        id_generator=FakeUserIdGenerator(),
        audit_log=FakeAuditLog(),
    )(CreateUserCommand(email="alice@example.com", raw_password="secret123"))


async def test_stores_token_and_sends_email() -> None:
    repo = FakeUserRepository()
    await _register(repo)
    token_store = FakePasswordResetTokenStore()
    mailer = FakeMailer()
    audit = FakeAuditLog()
    uc = _make_uc(repo, token_store, mailer, audit)

    await uc(StartPasswordResetCommand(email="alice@example.com"))

    assert len(mailer.sent) == 1
    assert mailer.sent[0][0] == "alice@example.com"
    assert len(mailer.sent[0][1]) > 0
    assert len(audit.events) == 1
    assert audit.events[0].event_type == AuditEventType.PASSWORD_RESET_REQUESTED


async def test_silently_succeeds_for_unknown_email() -> None:
    mailer = FakeMailer()
    uc = _make_uc(FakeUserRepository(), FakePasswordResetTokenStore(), mailer, FakeAuditLog())

    await uc(StartPasswordResetCommand(email="nobody@example.com"))

    assert mailer.sent == []
