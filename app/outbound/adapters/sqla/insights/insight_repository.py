from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.insights.ports.insight_repository import (
    MAX_RETRIES_EXCEEDED_ERROR,
    InsightAlreadyTerminalError,
    InsightNotFoundError,
    ReapedInsight,
    ReapResult,
)
from app.domain.entities.insight import Insight
from app.domain.value_objects.enums import InsightStatus, Period
from app.domain.value_objects.ids import InsightId, UserId
from app.outbound.persistence_sqla.mappings.insight import insights


class SqlaInsightRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, insight: Insight) -> None:
        try:
            await self._session.merge(insight)
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_by_id(self, insight_id: InsightId, user_id: UserId) -> Insight | None:
        try:
            result = await self._session.execute(
                select(Insight)
                .where(insights.c.id == insight_id)
                .where(insights.c.user_id == user_id)
            )
            return result.scalars().first()
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def claim_for_processing(
        self, insight_id: InsightId, user_id: UserId, deadline: datetime
    ) -> Insight:
        try:
            result = await self._session.execute(
                select(Insight)
                .where(insights.c.id == insight_id, insights.c.user_id == user_id)
                .with_for_update()
            )
            insight = result.scalars().first()
            if insight is None:
                raise InsightNotFoundError(str(insight_id))
            if insight.status != InsightStatus.QUEUED:
                # Already claimed by another worker, or row is durably terminal.
                # Distinguished from missing-row so the use case can exit cleanly
                # instead of looking like a transient failure.
                raise InsightAlreadyTerminalError(insight.status)
            insight.mark_processing()
            insight.processing_deadline = deadline
            await self._session.merge(insight)
            return insight
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def list_by_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[datetime, InsightId] | None,
        period: Period | None = None,
        period_year: int | None = None,
        period_month: int | None = None,
    ) -> list[Insight]:
        try:
            stmt = (
                select(Insight)
                .where(insights.c.user_id == user_id)
                .order_by(insights.c.created_at.desc(), insights.c.id.desc())
                .limit(limit)
            )
            if cursor is not None:
                cursor_created_at, cursor_id = cursor
                stmt = stmt.where(
                    (insights.c.created_at < cursor_created_at)
                    | ((insights.c.created_at == cursor_created_at) & (insights.c.id < cursor_id))
                )
            if period is not None:
                stmt = stmt.where(insights.c.period == period)
            if period_year is not None:
                stmt = stmt.where(insights.c.period_year == period_year)
            if period_month is not None:
                stmt = stmt.where(insights.c.period_month == period_month)
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def reap_expired_processing(self, max_retries: int) -> ReapResult:
        if max_retries < 1:
            raise ValueError(f"max_retries must be >= 1, got {max_retries}")
        try:
            requeued_result = await self._session.execute(
                sa.text(
                    "UPDATE insights"
                    "   SET status              = :queued,"
                    "       retry_count         = retry_count + 1,"
                    "       processing_deadline = NULL,"
                    "       updated_at          = now()"
                    " WHERE status = :processing"
                    "   AND processing_deadline < now()"
                    "   AND retry_count < :max"
                    " RETURNING id, user_id, period, period_year, period_month"
                ),
                {
                    "queued": InsightStatus.QUEUED,
                    "processing": InsightStatus.PROCESSING,
                    "max": max_retries,
                },
            )
            requeued = [
                ReapedInsight(
                    insight_id=InsightId(row["id"]),
                    user_id=UserId(row["user_id"]),
                    period=Period(row["period"]),
                    period_year=row["period_year"],
                    period_month=row["period_month"],
                )
                for row in requeued_result.mappings().all()
            ]

            exhausted_result = await self._session.execute(
                sa.text(
                    "UPDATE insights"
                    "   SET status        = :failed,"
                    "       error_message = :err,"
                    "       updated_at    = now()"
                    " WHERE status = :processing"
                    "   AND processing_deadline < now()"
                    "   AND retry_count >= :max"
                ),
                {
                    "failed": InsightStatus.FAILED,
                    "processing": InsightStatus.PROCESSING,
                    "max": max_retries,
                    "err": MAX_RETRIES_EXCEEDED_ERROR,
                },
            )
            exhausted_count = int(exhausted_result.rowcount or 0)  # type: ignore[attr-defined]

            return ReapResult(requeued=requeued, exhausted_count=exhausted_count)
        except SQLAlchemyError as exc:
            raise StorageError from exc
