from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.users.audit_event import AuditEvent
from app.application.users.ports.audit_log import AuditLog
from app.application.users.ports.session_store import SessionStore
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import SessionId, UserId


@dataclass(frozen=True, slots=True)
class LogoutCommand:
    session_id: SessionId
    user_id: UserId
    ip: str | None = None
    user_agent: str | None = None


class LogoutUseCase:
    def __init__(self, session_store: SessionStore, audit_log: AuditLog) -> None:
        self._session_store = session_store
        self._audit_log = audit_log

    async def __call__(self, command: LogoutCommand) -> None:
        await self._session_store.revoke(command.session_id, command.user_id)
        await self._audit_log.record(
            AuditEvent(
                event_type=AuditEventType.USER_LOGOUT,
                user_id=command.user_id,
                occurred_at=datetime.now(UTC),
                ip=command.ip,
                user_agent=command.user_agent,
            )
        )
