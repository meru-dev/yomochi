from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from app.domain.value_objects.ids import UserId

if TYPE_CHECKING:
    from app.application.users.use_cases.list_audit_events import AuditEventRow


class AuditEventReader(Protocol):
    @abstractmethod
    async def list_by_user(
        self,
        *,
        user_id: UserId,
        limit: int,
        cursor_occurred_at: datetime | None = None,
        cursor_id: str | None = None,
        event_type_filter: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list["AuditEventRow"]: ...
