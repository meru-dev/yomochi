from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.entities.alert import Alert, AlertType
from app.domain.value_objects.ids import AlertId, UserId


def _row_to_alert(row: Any) -> Alert:
    return Alert(
        id_=AlertId(row.id if isinstance(row.id, UUID) else UUID(str(row.id))),
        user_id=UserId(row.user_id if isinstance(row.user_id, UUID) else UUID(str(row.user_id))),
        alert_type=AlertType(row.type),
        title=row.title,
        body=row.body,
        metadata=row.metadata or {},
        period_year=row.period_year,
        period_month=row.period_month,
        is_read=row.is_read,
        created_at=row.created_at,
    )


class SqlaAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[datetime, AlertId] | None,
    ) -> list[Alert]:
        try:
            params: dict[str, Any] = {"user_id": str(user_id.value), "limit": limit}
            if cursor:
                cursor_dt, cursor_id = cursor
                params["cursor_dt"] = cursor_dt
                params["cursor_id"] = str(cursor_id.value)
                stmt = sa.text("""
                    SELECT id, user_id, type, title, body, metadata,
                           period_year, period_month, is_read, created_at
                    FROM user_alerts
                    WHERE user_id = :user_id
                      AND (created_at, id::text) < (:cursor_dt, :cursor_id)
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                """)
            else:
                stmt = sa.text("""
                    SELECT id, user_id, type, title, body, metadata,
                           period_year, period_month, is_read, created_at
                    FROM user_alerts
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                """)
            rows = (await self._session.execute(stmt, params)).fetchall()
            return [_row_to_alert(r) for r in rows]
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def unread_count(self, user_id: UserId) -> int:
        try:
            result = await self._session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM user_alerts WHERE user_id = :uid AND is_read = FALSE"
                ),
                {"uid": str(user_id.value)},
            )
            return int(result.scalar_one())
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def mark_read(self, alert_id: AlertId, user_id: UserId) -> bool:
        try:
            result = await self._session.execute(
                sa.text("""
                    UPDATE user_alerts
                    SET is_read = TRUE
                    WHERE id = :id AND user_id = :user_id
                    RETURNING id
                """),
                {"id": str(alert_id.value), "user_id": str(user_id.value)},
            )
            return result.fetchone() is not None
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def clear_all(self, user_id: UserId) -> None:
        try:
            await self._session.execute(
                sa.text("DELETE FROM user_alerts WHERE user_id = :uid"),
                {"uid": str(user_id.value)},
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def purge_older_than(self, days: int) -> int:
        if days < 1:
            raise ValueError(f"days must be >= 1, got {days}")
        try:
            result = await self._session.execute(
                sa.text(
                    "DELETE FROM user_alerts"
                    " WHERE created_at < now() - make_interval(days => :days)"
                ),
                {"days": days},
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]
        except SQLAlchemyError as exc:
            raise StorageError from exc
