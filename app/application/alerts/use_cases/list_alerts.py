from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.alerts.ports.alert_repository import AlertRepository
from app.application.common.cursor import decode_cursor, encode_cursor
from app.domain.entities.alert import Alert
from app.domain.value_objects.ids import AlertId, UserId


@dataclass(frozen=True, slots=True)
class ListAlertsQuery:
    user_id: UserId
    limit: int = 20
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ListAlertsResult:
    alerts: tuple[Alert, ...]
    next_cursor: str | None
    unread_count: int


def _encode_cursor(alert: Alert) -> str:
    return encode_cursor({"created_at": alert.created_at.isoformat(), "id": str(alert.id_.value)})


def _decode_cursor(cursor: str) -> tuple[datetime, AlertId]:
    raw = decode_cursor(cursor)
    return datetime.fromisoformat(raw["created_at"]), AlertId(UUID(raw["id"]))


class ListAlertsUseCase:
    def __init__(self, repo: AlertRepository) -> None:
        self._repo = repo

    async def __call__(self, query: ListAlertsQuery) -> ListAlertsResult:
        cursor_tuple = _decode_cursor(query.cursor) if query.cursor else None
        alerts = await self._repo.list_for_user(
            user_id=query.user_id,
            limit=query.limit,
            cursor=cursor_tuple,
        )
        next_cursor = _encode_cursor(alerts[-1]) if len(alerts) == query.limit > 0 else None
        unread = await self._repo.unread_count(query.user_id)
        return ListAlertsResult(
            alerts=tuple(alerts),
            next_cursor=next_cursor,
            unread_count=unread,
        )
