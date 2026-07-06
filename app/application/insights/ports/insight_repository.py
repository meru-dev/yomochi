from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.entities.insight import Insight
from app.domain.value_objects.enums import InsightStatus, Period
from app.domain.value_objects.ids import InsightId, UserId

MAX_RETRIES_EXCEEDED_ERROR = "max retries exceeded"


class InsightNotFoundError(Exception): ...


class InsightAlreadyTerminalError(Exception):
    """The Insight exists but is not in a claimable state (already PROCESSING/COMPLETED/FAILED).

    Carries the current status so the caller can distinguish 'in-flight' from
    'durably done' and decide whether to retry or treat as terminal-success.
    """

    def __init__(self, status: InsightStatus) -> None:
        self.status = status
        super().__init__(f"insight already in terminal/in-flight state: {status.value}")


@dataclass(frozen=True, slots=True)
class ReapedInsight:
    """Operational snapshot of a requeued Insight — enough to re-emit InsightRequested."""

    insight_id: InsightId
    user_id: UserId
    period: Period
    period_year: int
    period_month: int


@dataclass(frozen=True, slots=True)
class ReapResult:
    requeued: list[ReapedInsight]
    exhausted_count: int


class InsightRepository(Protocol):
    @abstractmethod
    async def save(self, insight: Insight) -> None: ...

    @abstractmethod
    async def get_by_id(self, insight_id: InsightId, user_id: UserId) -> Insight | None: ...

    @abstractmethod
    async def claim_for_processing(
        self, insight_id: InsightId, user_id: UserId, deadline: datetime
    ) -> Insight:
        """Atomically transition a QUEUED Insight to PROCESSING.

        Returns the claimed Insight (`status == PROCESSING`).
        Raises `InsightNotFoundError` when the row does not exist.
        Raises `InsightAlreadyTerminalError` when the row exists but is already
        PROCESSING/COMPLETED/FAILED — letting the caller distinguish 'durably done'
        from 'missing' and avoid spurious DLQ.
        """
        ...

    @abstractmethod
    async def list_by_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[datetime, InsightId] | None,
        period: Period | None = None,
        period_year: int | None = None,
        period_month: int | None = None,
    ) -> list[Insight]: ...

    @abstractmethod
    async def reap_expired_processing(self, max_retries: int) -> ReapResult:
        """Recover orphaned PROCESSING insights whose lease has expired.

        Two passes in one TX:
          - retry_count < max_retries → requeue (status='queued', retry_count++,
            clear processing_deadline). Returned in `requeued` for outbox re-emit.
          - retry_count >= max_retries → fail (status='failed', error_message set).
            Counted in `exhausted_count`.

        Operational metadata (`retry_count`, `processing_deadline`) is owned here,
        not by the domain entity (Sidekiq/Celery precedent).
        """
        ...
