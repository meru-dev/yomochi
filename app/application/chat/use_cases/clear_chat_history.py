# app/application/chat/use_cases/clear_chat_history.py
from dataclasses import dataclass

from app.application.chat.ports.chat_history_store import ChatHistoryStore
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class ClearChatHistoryCommand:
    user_id: UserId


class ClearChatHistoryUseCase:
    def __init__(self, store: ChatHistoryStore) -> None:
        self._store = store

    async def __call__(self, command: ClearChatHistoryCommand) -> None:
        await self._store.clear_all(command.user_id)
