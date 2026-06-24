from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from app.application.chat.ports.chat_history_store import ChatHistoryStore


@dataclass(frozen=True, slots=True)
class ChatWorkUnit:
    """Session-bound ports needed inside one short TX scope for the chat path."""

    history_store: ChatHistoryStore


class ChatWorkUnitFactory(Protocol):
    """Open a fresh unit-of-work scope backed by the app session factory.

    Each call opens its own short transaction so the DB connection is released
    before any LLM network call. Usage:

        async with factory() as uow:
            history = await uow.history_store.last_n(...)
        # commit on success, rollback on exception
    """

    @abstractmethod
    def __call__(self) -> AbstractAsyncContextManager[ChatWorkUnit]: ...
