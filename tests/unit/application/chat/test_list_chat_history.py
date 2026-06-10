# tests/unit/application/chat/test_list_chat_history.py
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.use_cases.list_chat_history import (
    ListChatHistoryQuery,
    ListChatHistoryUseCase,
)
from app.domain.value_objects.ids import UserId

_UID = UserId(uuid.uuid4())


def _turn(i: int) -> ChatTurn:
    return ChatTurn(
        id=uuid.uuid4(),
        user_id=_UID,
        role="user",
        content=f"message {i}",
        chunks_used=(),
        created_at=datetime(2026, 5, i + 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_returns_empty():
    store = AsyncMock()
    store.list_for_user = AsyncMock(return_value=[])
    uc = ListChatHistoryUseCase(store)
    result = await uc(ListChatHistoryQuery(user_id=_UID))
    assert result.turns == ()
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_returns_next_cursor_on_full_page():
    turns = [_turn(i) for i in range(20)]
    store = AsyncMock()
    store.list_for_user = AsyncMock(return_value=turns)
    uc = ListChatHistoryUseCase(store)
    result = await uc(ListChatHistoryQuery(user_id=_UID, limit=20))
    assert result.next_cursor is not None


@pytest.mark.asyncio
async def test_no_next_cursor_on_partial_page():
    store = AsyncMock()
    store.list_for_user = AsyncMock(return_value=[_turn(0)])
    uc = ListChatHistoryUseCase(store)
    result = await uc(ListChatHistoryQuery(user_id=_UID, limit=20))
    assert result.next_cursor is None
