from dataclasses import dataclass
from datetime import datetime

from app.domain.entities.base import EntityMixin
from app.domain.value_objects.budget_summary_snapshot import BudgetSummarySnapshot
from app.domain.value_objects.enums import ContextQuality, InsightStatus, Period
from app.domain.value_objects.ids import InsightId, UserId


@dataclass(eq=False)
class Insight(EntityMixin):
    id_: InsightId
    user_id: UserId
    period: Period
    period_year: int
    period_month: int  # 1-12 (for MONTHLY); ISO week number (for WEEKLY)
    status: InsightStatus
    context_quality: ContextQuality | None
    title: str | None
    description: str | None
    impact_score: int | None  # 1-10
    generated_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime | None = None
    budget_summary: BudgetSummarySnapshot | None = None
    processing_deadline: datetime | None = None
    retry_count: int = 0

    def mark_queued(self) -> None:
        if self.status != InsightStatus.PENDING:
            msg = f"Cannot queue insight in status {self.status}"
            raise ValueError(msg)
        self.status = InsightStatus.QUEUED

    def mark_processing(self, deadline: datetime | None = None) -> None:
        if self.status != InsightStatus.QUEUED:
            msg = f"Cannot process insight in status {self.status}"
            raise ValueError(msg)
        self.status = InsightStatus.PROCESSING
        if deadline is not None:
            self.processing_deadline = deadline

    def mark_completed(
        self,
        title: str,
        description: str,
        impact_score: int,
        context_quality: ContextQuality,
        generated_at: datetime,
        budget_summary: BudgetSummarySnapshot | None = None,
    ) -> None:
        if self.status != InsightStatus.PROCESSING:
            msg = f"Cannot complete insight in status {self.status}"
            raise ValueError(msg)
        if not (1 <= impact_score <= 10):
            msg = f"impact_score must be 1-10, got {impact_score}"
            raise ValueError(msg)
        self.status = InsightStatus.COMPLETED
        self.title = title
        self.description = description
        self.impact_score = impact_score
        self.context_quality = context_quality
        self.generated_at = generated_at
        self.budget_summary = budget_summary

    def mark_failed(self, error: str) -> None:
        if self.status != InsightStatus.PROCESSING:
            msg = f"Cannot fail insight in status {self.status}"
            raise ValueError(msg)
        self.status = InsightStatus.FAILED
        self.error_message = error
