from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.insights.ports.work_unit import InsightWorkUnit
from app.outbound.adapters.sqla.insights.budget_summary_reader import SqlaBudgetSummaryReader
from app.outbound.adapters.sqla.insights.insight_repository import SqlaInsightRepository


class SqlaInsightWorkUnitFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    def __call__(self) -> AbstractAsyncContextManager[InsightWorkUnit]:
        return self._scope()

    @asynccontextmanager
    async def _scope(self) -> AsyncIterator[InsightWorkUnit]:
        async with self._factory.begin() as session:
            yield InsightWorkUnit(
                insight_repo=SqlaInsightRepository(session),
                budget_reader=SqlaBudgetSummaryReader(session),
            )
