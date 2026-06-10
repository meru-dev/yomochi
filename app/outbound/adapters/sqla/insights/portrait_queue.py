import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.value_objects.ids import UserId


class SqlaPortraitQueue:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pop_dirty(self, limit: int) -> list[UserId]:
        try:
            result = await self._session.execute(
                sa.text(
                    """
                    DELETE FROM portrait_queue
                    WHERE user_id IN (
                        SELECT user_id FROM portrait_queue
                        ORDER BY marked_at
                        LIMIT :limit
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING user_id
                    """
                ),
                {"limit": limit},
            )
            return [UserId(row.user_id) for row in result.fetchall()]
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def mark_dirty(self, user_id: UserId) -> None:
        try:
            await self._session.execute(
                sa.text(
                    """
                    INSERT INTO portrait_queue (user_id, marked_at)
                    VALUES (:uid, now())
                    ON CONFLICT (user_id) DO UPDATE SET marked_at = now()
                    """
                ),
                {"uid": str(user_id.value)},
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def mark_all_dirty(self) -> int:
        try:
            result = await self._session.execute(
                sa.text(
                    """
                    INSERT INTO portrait_queue (user_id, marked_at)
                    SELECT id, now() FROM users
                    ON CONFLICT (user_id) DO UPDATE SET marked_at = now()
                    """
                )
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]
        except SQLAlchemyError as exc:
            raise StorageError from exc
