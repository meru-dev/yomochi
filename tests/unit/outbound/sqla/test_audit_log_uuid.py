import uuid
from unittest.mock import AsyncMock

import pytest

from app.application.users.audit_event import AuditEvent
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.users.audit_log import SqlaAuditLog


@pytest.mark.asyncio
async def test_audit_log_uses_uuid7_not_uuid4() -> None:
    """All IDs generated in SqlaAuditLog must be uuid7 (version 7)."""
    import datetime

    session = AsyncMock()
    session.execute = AsyncMock()

    log = SqlaAuditLog(session)
    event = AuditEvent(
        event_type=AuditEventType.USER_LOGIN,
        user_id=UserId(uuid.uuid4()),
        occurred_at=datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC),
        ip="1.2.3.4",
        user_agent="pytest",
    )
    await log.record(event)

    call_args = session.execute.await_args
    params = call_args.args[1]
    generated_id = params["id"]
    assert isinstance(generated_id, uuid.UUID), "id must be a uuid.UUID"
    assert generated_id.version == 7, f"expected uuid7, got version {generated_id.version}"
