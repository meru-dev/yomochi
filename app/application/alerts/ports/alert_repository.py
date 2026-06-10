from datetime import datetime
from typing import Protocol

from app.domain.entities.alert import Alert
from app.domain.value_objects.ids import AlertId, UserId


class AlertRepository(Protocol):
    async def list_for_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[datetime, AlertId] | None,
    ) -> list[Alert]: ...

    async def unread_count(self, user_id: UserId) -> int: ...

    async def mark_read(self, alert_id: AlertId, user_id: UserId) -> bool:
        """Returns True if alert was found and updated, False if not found or not owned."""
        ...

    async def clear_all(self, user_id: UserId) -> None: ...

    async def purge_older_than(self, days: int) -> int:
        """Delete alerts older than `days`. Returns the number of rows deleted."""
        ...
