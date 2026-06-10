from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.users.use_cases.list_audit_events import AuditEventRow
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import UserId


class SqlaAuditEventReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
    ) -> list[AuditEventRow]:
        params: dict[str, object] = {"user_id": str(user_id), "limit": limit}
        clauses: list[str] = ["user_id = :user_id"]

        if cursor_occurred_at is not None and cursor_id is not None:
            clauses.append("(occurred_at, id::text) < (:cursor_at, :cursor_id)")
            params["cursor_at"] = cursor_occurred_at
            params["cursor_id"] = cursor_id

        if event_type_filter is not None:
            clauses.append("event_type = :event_type")
            params["event_type"] = event_type_filter

        if from_date is not None:
            clauses.append("occurred_at >= :from_date")
            params["from_date"] = from_date

        if to_date is not None:
            clauses.append("occurred_at <= :to_date")
            params["to_date"] = to_date

        where = " AND ".join(clauses)
        sql = text(
            f"SELECT id, event_type, occurred_at, ip::text, user_agent"  # noqa: S608
            f" FROM audit_events"
            f" WHERE {where}"
            f" ORDER BY occurred_at DESC, id DESC"
            f" LIMIT :limit"
        )

        try:
            result = await self._session.execute(sql, params)
        except SQLAlchemyError as exc:
            raise StorageError from exc

        rows: list[AuditEventRow] = []
        for row in result.fetchall():
            rows.append(
                AuditEventRow(
                    id=str(row.id),
                    event_type=AuditEventType(row.event_type),
                    occurred_at=row.occurred_at,
                    ip=row.ip,
                    user_agent=row.user_agent,
                )
            )
        return rows
