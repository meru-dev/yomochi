from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from app.application.insights.ports.alert_writer import AlertWriter
from app.application.insights.ports.budget_summary_reader import BudgetSummaryReader
from app.application.insights.ports.chunk_retriever import ChunkRetriever
from app.application.insights.ports.chunk_writer import ChunkWriter
from app.application.insights.ports.dirty_period_repository import DirtyPeriodRepository
from app.application.insights.ports.insight_repository import InsightRepository


@dataclass(frozen=True, slots=True)
class InsightWorkUnit:
    """All ports needed inside one TX scope for the insight pipeline."""

    insight_repo: InsightRepository
    chunk_writer: ChunkWriter
    chunk_retriever: ChunkRetriever
    budget_reader: BudgetSummaryReader
    alert_writer: AlertWriter
    dirty_period_repo: DirtyPeriodRepository


class InsightWorkUnitFactory(Protocol):
    """Open a fresh unit-of-work scope.

    Usage:
        async with factory() as uow:
            insight = await uow.insight_repo.claim_for_processing(...)
        # commit on success, rollback on exception
    """

    @abstractmethod
    def __call__(self) -> AbstractAsyncContextManager[InsightWorkUnit]: ...
