from dataclasses import dataclass
from datetime import datetime

from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_type: AuditEventType
    user_id: UserId | None
    occurred_at: datetime
    ip: str | None = None
    user_agent: str | None = None
