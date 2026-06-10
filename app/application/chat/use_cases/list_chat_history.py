# app/application/chat/use_cases/list_chat_history.py
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.chat.ports.chat_history_store import (
    ChatHistoryStore,
    ChatTurn,
    decode_cursor,
    encode_cursor,
)
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class ListChatHistoryQuery:
    user_id: UserId
    limit: int = 20
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ListChatHistoryResult:
    turns: tuple[ChatTurn, ...]
    next_cursor: str | None


class ListChatHistoryUseCase:
    def __init__(self, store: ChatHistoryStore) -> None:
        self._store = store

    async def __call__(self, query: ListChatHistoryQuery) -> ListChatHistoryResult:
        cursor_tuple: tuple[datetime, UUID] | None = None
        if query.cursor:
            cursor_tuple = decode_cursor(query.cursor)

        turns = await self._store.list_for_user(
            user_id=query.user_id,
            limit=query.limit,
            cursor=cursor_tuple,
        )
        next_cursor = encode_cursor(turns[-1]) if turns and len(turns) == query.limit else None
        return ListChatHistoryResult(turns=tuple(turns), next_cursor=next_cursor)
