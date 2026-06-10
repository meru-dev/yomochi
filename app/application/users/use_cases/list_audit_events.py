from dataclasses import dataclass, field
from datetime import datetime

from app.application.common.cursor import decode_cursor, encode_cursor
from app.application.users.ports.audit_event_reader import AuditEventReader
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class AuditEventRow:
    id: str
    event_type: AuditEventType
    occurred_at: datetime
    ip: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class ListAuditEventsQuery:
    user_id: UserId
    limit: int = field(default=50)
    cursor: str | None = field(default=None)
    event_type_filter: str | None = field(default=None)
    from_date: datetime | None = field(default=None)
    to_date: datetime | None = field(default=None)


@dataclass(frozen=True, slots=True)
class ListAuditEventsResult:
    events: tuple[AuditEventRow, ...]
    next_cursor: str | None


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    raw = decode_cursor(cursor)
    return datetime.fromisoformat(raw["occurred_at"]), raw["id"]


def _encode_cursor(row: AuditEventRow) -> str:
    return encode_cursor({"occurred_at": row.occurred_at.isoformat(), "id": row.id})


class ListAuditEventsUseCase:
    def __init__(self, audit_event_reader: AuditEventReader) -> None:
        self._reader = audit_event_reader

    async def __call__(self, query: ListAuditEventsQuery) -> ListAuditEventsResult:
        cursor_occurred_at: datetime | None = None
        cursor_id: str | None = None
        if query.cursor:
            cursor_occurred_at, cursor_id = _decode_cursor(query.cursor)

        rows = await self._reader.list_by_user(
            user_id=query.user_id,
            limit=query.limit + 1,
            cursor_occurred_at=cursor_occurred_at,
            cursor_id=cursor_id,
            event_type_filter=query.event_type_filter,
            from_date=query.from_date,
            to_date=query.to_date,
        )

        has_more = len(rows) > query.limit
        page = rows[: query.limit]
        next_cursor = _encode_cursor(page[-1]) if has_more else None
        return ListAuditEventsResult(events=tuple(page), next_cursor=next_cursor)
