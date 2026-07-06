from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.chat.ports.work_unit import ChatWorkUnit
from app.outbound.adapters.sqla.chat.chat_history_store import SqlaChatHistoryStore


class SqlaChatWorkUnitFactory:
    """Hands out a per-call UoW backed by an async_sessionmaker.

    Each call opens its own `async with session_factory.begin()` and yields the
    chat adapter bundle. The TX commits on clean exit and rolls back on exception,
    so the pooled connection is released between calls — never held across the
    LLM call.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    def __call__(self) -> AbstractAsyncContextManager[ChatWorkUnit]:
        return self._scope()

    @asynccontextmanager
    async def _scope(self) -> AsyncIterator[ChatWorkUnit]:
        async with self._factory.begin() as session:
            yield ChatWorkUnit(
                history_store=SqlaChatHistoryStore(session),
            )
