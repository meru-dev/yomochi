from dataclasses import dataclass
from datetime import datetime

from app.domain.value_objects.ids import SessionId, UserId


@dataclass(frozen=True, slots=True)
class Session:
    id_: SessionId
    user_id: UserId
    expires_at: datetime
    user_agent: str
    ip: str
