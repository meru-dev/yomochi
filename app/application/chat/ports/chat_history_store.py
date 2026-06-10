from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.application.common.cursor import decode_cursor as _decode_raw
from app.application.common.cursor import encode_cursor as _encode_raw
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True)
class ChatTurn:
    id: UUID
    user_id: UserId
    role: str  # 'user' | 'assistant'
    content: str
    chunks_used: tuple[dict[str, Any], ...]  # ({chunk_type, period_label}, ...)
    created_at: datetime


def encode_cursor(turn: ChatTurn) -> str:
    return _encode_raw({"created_at": turn.created_at.isoformat(), "id": str(turn.id)})


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = _decode_raw(cursor)
    try:
        return datetime.fromisoformat(raw["created_at"]), UUID(raw["id"])
    except (ValueError, KeyError) as exc:
        from app.domain.exceptions.domain_errors import InvalidCursorError

        raise InvalidCursorError("Invalid or expired pagination cursor") from exc


class ChatHistoryStore(Protocol):
    async def last_n(self, user_id: UserId, n: int) -> list[ChatTurn]: ...

    async def save_turns(self, user_id: UserId, turns: list[ChatTurn]) -> None: ...

    async def append_turn_pair(
        self, user_id: UserId, user_turn: ChatTurn, assistant_turn: ChatTurn
    ) -> tuple[ChatTurn, ChatTurn]:
        """Persist a (user, assistant) exchange. The adapter guarantees the
        assistant turn sorts after the user turn for cursor-paginated reads,
        even when both turns were constructed at the same instant. Returns
        the as-stored pair (the assistant `created_at` may be adjusted)."""
        ...

    async def list_for_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> list[ChatTurn]: ...

    async def clear_all(self, user_id: UserId) -> None: ...
