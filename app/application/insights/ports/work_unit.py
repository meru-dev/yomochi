from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from app.application.insights.ports.budget_summary_reader import BudgetSummaryReader
from app.application.insights.ports.insight_repository import InsightRepository


@dataclass(frozen=True, slots=True)
class InsightWorkUnit:
    """Ports needed inside one TX scope for the deterministic insight pipeline.

    The pipeline reads the period (and its 3-month history) via ``budget_reader``
    and claims / completes / fails the insight row via ``insight_repo``. It writes
    no chunks and marks no dirty periods — those subsystems were removed.
    """

    insight_repo: InsightRepository
    budget_reader: BudgetSummaryReader


class InsightWorkUnitFactory(Protocol):
    """Open a fresh unit-of-work scope.

    Usage:
        async with factory() as uow:
            insight = await uow.insight_repo.claim_for_processing(...)
        # commit on success, rollback on exception
    """

    @abstractmethod
    def __call__(self) -> AbstractAsyncContextManager[InsightWorkUnit]: ...
