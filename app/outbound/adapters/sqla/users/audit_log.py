from uuid import UUID

import uuid_utils
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.audit_event import AuditEvent
from app.application.common.exceptions import StorageError


class SqlaAuditLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: AuditEvent) -> None:
        try:
            await self._session.execute(
                text(
                    "INSERT INTO audit_events"
                    " (id, event_type, user_id, occurred_at, ip, user_agent)"
                    " VALUES (:id, :event_type, :user_id, :occurred_at, :ip, :user_agent)"
                ),
                {
                    "id": UUID(str(uuid_utils.uuid7())),
                    "event_type": event.event_type.value,
                    "user_id": event.user_id.value if event.user_id else None,
                    "occurred_at": event.occurred_at,
                    "ip": event.ip,
                    "user_agent": event.user_agent,
                },
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc
