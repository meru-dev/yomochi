from datetime import UTC, datetime, timedelta

from app.application.users.session import Session
from app.application.users.use_cases.logout import LogoutCommand, LogoutUseCase
from app.domain.value_objects.enums import AuditEventType
from tests.fakes.id_generator import FakeSessionIdGenerator, FakeUserIdGenerator
from tests.fakes.repositories import FakeAuditLog, FakeSessionStore


async def test_logout_revokes_session_and_records_audit() -> None:
    session_store = FakeSessionStore()
    audit = FakeAuditLog()
    session_id_gen = FakeSessionIdGenerator()
    user_id_gen = FakeUserIdGenerator()

    session = Session(
        id_=session_id_gen(),
        user_id=user_id_gen(),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_agent="agent",
        ip="1.2.3.4",
    )
    await session_store.save(session)

    uc = LogoutUseCase(session_store=session_store, audit_log=audit)
    await uc(LogoutCommand(session_id=session.id_, user_id=session.user_id, ip="1.2.3.4"))

    remaining = await session_store.list_active(session.user_id)
    assert remaining == []
    assert len(audit.events) == 1
    assert audit.events[0].event_type == AuditEventType.USER_LOGOUT
    assert audit.events[0].user_id == session.user_id
