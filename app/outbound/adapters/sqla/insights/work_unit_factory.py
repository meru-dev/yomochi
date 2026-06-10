from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.insights.ports.work_unit import InsightWorkUnit
from app.outbound.adapters.sqla.alerts.alert_writer import SqlaAlertWriter
from app.outbound.adapters.sqla.insights.budget_summary_reader import SqlaBudgetSummaryReader
from app.outbound.adapters.sqla.insights.chunk_retriever import SqlaChunkRetriever
from app.outbound.adapters.sqla.insights.chunk_writer import SqlaChunkWriter
from app.outbound.adapters.sqla.insights.dirty_period_repository import SqlaDirtyPeriodRepository
from app.outbound.adapters.sqla.insights.insight_repository import SqlaInsightRepository


class SqlaInsightWorkUnitFactory:
    """Hands out a per-call UoW backed by an async_sessionmaker.

    Each call opens its own `async with session_factory.begin()` and yields the
    adapter bundle. The TX commits on clean exit and rolls back on exception.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    def __call__(self) -> AbstractAsyncContextManager[InsightWorkUnit]:
        return self._scope()

    @asynccontextmanager
    async def _scope(self) -> AsyncIterator[InsightWorkUnit]:
        async with self._factory.begin() as session:
            yield InsightWorkUnit(
                insight_repo=SqlaInsightRepository(session),
                chunk_writer=SqlaChunkWriter(session),
                chunk_retriever=SqlaChunkRetriever(session),
                budget_reader=SqlaBudgetSummaryReader(session),
                alert_writer=SqlaAlertWriter(session),
                dirty_period_repo=SqlaDirtyPeriodRepository(session),
            )
