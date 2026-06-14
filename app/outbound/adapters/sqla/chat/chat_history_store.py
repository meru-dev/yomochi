import json
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.common.exceptions import StorageError
from app.domain.value_objects.ids import UserId


def _row_to_turn(row: Any, user_id: UserId) -> ChatTurn:
    raw_id = row.id
    turn_id = raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id))
    chunks = row.chunks_used if isinstance(row.chunks_used, list) else []
    return ChatTurn(
        id=turn_id,
        user_id=user_id,
        role=row.role,
        content=row.content,
        chunks_used=tuple(chunks),
        created_at=row.created_at,
    )


class SqlaChatHistoryStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def last_n(self, user_id: UserId, n: int) -> list[ChatTurn]:
        try:
            rows = (
                await self._session.execute(
                    sa.text("""
                        SELECT id, role, content, chunks_used, created_at
                        FROM chat_turns
                        WHERE user_id = :uid
                        ORDER BY created_at DESC, id DESC
                        LIMIT :n
                    """),
                    {"uid": str(user_id.value), "n": n},
                )
            ).fetchall()
            return list(reversed([_row_to_turn(r, user_id) for r in rows]))
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def append_turn_pair(
        self, user_id: UserId, user_turn: ChatTurn, assistant_turn: ChatTurn
    ) -> tuple[ChatTurn, ChatTurn]:
        # Persist both turns as-is. Ordering is the use case's responsibility:
        # it stamps the assistant turn via a later clock.now(), and the monotone
        # UUID7 ids break any (created_at) ties under the (created_at, id) sort.
        await self.save_turns(user_id, [user_turn, assistant_turn])
        return user_turn, assistant_turn

    async def save_turns(self, user_id: UserId, turns: list[ChatTurn]) -> None:
        try:
            for turn in turns:
                await self._session.execute(
                    sa.text("""
                        INSERT INTO chat_turns (id, user_id, role, content, chunks_used, created_at)
                        VALUES (:id, :uid, :role, :content, CAST(:chunks AS jsonb), :created_at)
                    """),
                    {
                        "id": str(turn.id),
                        "uid": str(user_id.value),
                        "role": turn.role,
                        "content": turn.content,
                        "chunks": json.dumps(list(turn.chunks_used)),
                        "created_at": turn.created_at,
                    },
                )
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def list_for_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[datetime, uuid.UUID] | None,
    ) -> list[ChatTurn]:
        try:
            params: dict[str, Any] = {"uid": str(user_id.value), "limit": limit}
            if cursor:
                cursor_dt, cursor_id = cursor
                params["cursor_dt"] = cursor_dt
                params["cursor_id"] = str(cursor_id)
                stmt = sa.text("""
                    SELECT id, role, content, chunks_used, created_at
                    FROM chat_turns
                    WHERE user_id = :uid
                      AND (created_at, id) < (:cursor_dt, CAST(:cursor_id AS uuid))
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                """)
            else:
                stmt = sa.text("""
                    SELECT id, role, content, chunks_used, created_at
                    FROM chat_turns
                    WHERE user_id = :uid
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                """)
            rows = (await self._session.execute(stmt, params)).fetchall()
            return [_row_to_turn(r, user_id) for r in rows]
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def clear_all(self, user_id: UserId) -> None:
        try:
            await self._session.execute(
                sa.text("DELETE FROM chat_turns WHERE user_id = :uid"),
                {"uid": str(user_id.value)},
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc
