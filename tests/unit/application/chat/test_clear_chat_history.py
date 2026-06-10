# tests/unit/application/chat/test_clear_chat_history.py
import uuid
from unittest.mock import AsyncMock

import pytest

from app.application.chat.use_cases.clear_chat_history import (
    ClearChatHistoryCommand,
    ClearChatHistoryUseCase,
)
from app.domain.value_objects.ids import UserId


@pytest.mark.asyncio
async def test_calls_store_clear_all():
    store = AsyncMock()
    store.clear_all = AsyncMock()
    uid = UserId(uuid.uuid4())
    uc = ClearChatHistoryUseCase(store)
    await uc(ClearChatHistoryCommand(user_id=uid))
    store.clear_all.assert_called_once_with(uid)
