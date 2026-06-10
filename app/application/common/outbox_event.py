from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_type: str
    aggregate_id: str
    payload: dict[str, object]
    occurred_at: datetime
    user_id: UUID
