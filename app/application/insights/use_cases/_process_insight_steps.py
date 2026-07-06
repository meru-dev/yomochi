import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from opentelemetry import trace

from app.application.insights.ports.ai_insight_client import InsightResponse
from app.application.insights.ports.insight_context import InsightContextChunk
from app.application.insights.ports.insight_repository import InsightNotFoundError
from app.application.insights.ports.work_unit import InsightWorkUnitFactory
from app.domain.services.behavioral_shift_detector import (
    BehavioralShiftDetector,
    DetectedShift,
    format_shift_text,
)
from app.domain.services.monthly_aggregator import (
    MonthlyAggregation,
    TransactionRow,
    aggregate,
    format_monthly_summary,
)
from app.domain.value_objects.budget_summary_snapshot import BudgetSummarySnapshot
from app.domain.value_objects.enums import ContextQuality, Period
from app.domain.value_objects.ids import InsightId, UserId

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass(frozen=True, slots=True)
class ClaimedInsight:
    """Snapshot of fields needed outside the claim TX scope."""

    period: Period
    period_year: int
    period_month: int


@dataclass(frozen=True, slots=True)
class AssembledContext:
    chunks: list[InsightContextChunk]
    quality: ContextQuality


async def claim_insight(
    uow_factory: InsightWorkUnitFactory,
    insight_id: InsightId,
    user_id: UserId,
    lease_minutes: int,
) -> ClaimedInsight:
    """TX1: claim PROCESSING with a lease deadline.

    `user_id` is enforced at the repo layer (defense-in-depth in addition to the
    HTTP boundary). Wrong owner → `InsightNotFoundError`, not silent claim.

    Raises `InsightAlreadyTerminalError` (from the repo) when an event is
    re-delivered for a row already in COMPLETED / FAILED, or for a PROCESSING row
    whose lease is still live (another worker is active).
    """
    deadline = datetime.now(UTC) + timedelta(minutes=lease_minutes)
    async with uow_factory() as uow:
        insight = await uow.insight_repo.claim_for_processing(insight_id, user_id, deadline)
        return ClaimedInsight(
            period=insight.period,
            period_year=insight.period_year,
            period_month=insight.period_month,
        )


_N_HISTORY_MONTHS = 3


async def build_insight_context(
    uow_factory: InsightWorkUnitFactory,
    shift_detector: BehavioralShiftDetector,
    *,
    user_id: UserId,
    period_year: int,
    period_month: int,
) -> AssembledContext:
    """Deterministic context builder — no embedder, no ANN search, no portrait.

    Reads the period's transactions and 3-month history from SQL, runs the
    aggregation + shift-detection logic, then formats the results directly into
    pseudo-chunks for the AI client.

    Quality classification:
    - NONE    → no rows for the period  → caller records failure, AI not called.
    - FULL    → rows present + shifts detected.
    - PARTIAL → rows present, no shifts.
    """
    with tracer.start_as_current_span("deterministic_context"):
        async with uow_factory() as uow:
            rows = await uow.budget_reader.read_month(user_id, period_year, period_month)
            if not rows:
                return AssembledContext(chunks=[], quality=ContextQuality.NONE)

            history_raw = await uow.budget_reader.read_history_months(
                user_id, period_year, period_month, _N_HISTORY_MONTHS
            )

    # Aggregate current month
    current_aggs: list[MonthlyAggregation] = aggregate(
        period_year,
        period_month,
        [
            TransactionRow(
                amount=r.amount,
                currency=r.currency,
                type_=r.type_,
                category_label=r.category_label,
                day_of_month=r.day_of_month,
            )
            for r in rows
        ],
    )

    # Aggregate history months
    history_aggs: list[MonthlyAggregation] = []
    for (hy, hm), hrows in sorted(history_raw.items()):
        if hrows:
            history_aggs.extend(
                aggregate(
                    hy,
                    hm,
                    [
                        TransactionRow(
                            amount=r.amount,
                            currency=r.currency,
                            type_=r.type_,
                            category_label=r.category_label,
                            day_of_month=r.day_of_month,
                        )
                        for r in hrows
                    ],
                )
            )

    period_label = f"{period_year}-{period_month:02d}"

    # Build monthly_summary pseudo-chunk
    summary_text = format_monthly_summary(current_aggs)
    chunks: list[InsightContextChunk] = [
        InsightContextChunk(
            content=summary_text,
            chunk_type="monthly_summary",
            period_label=period_label,
            metadata={"year": period_year, "month": period_month},
        )
    ]

    # Detect shifts and optionally build behavioral_shift pseudo-chunk
    shifts: list[DetectedShift] = []
    if current_aggs:
        primary = current_aggs[0]
        same_currency_history = [h for h in history_aggs if h.currency == primary.currency]
        shifts = shift_detector.detect(primary, same_currency_history)
        if shifts:
            shift_text = format_shift_text(primary, shifts)
            chunks.append(
                InsightContextChunk(
                    content=shift_text,
                    chunk_type="behavioral_shift",
                    period_label=period_label,
                    metadata={
                        "year": period_year,
                        "month": period_month,
                        "shifts": [s.to_metadata() for s in shifts],
                    },
                )
            )

    quality = ContextQuality.FULL if shifts else ContextQuality.PARTIAL
    return AssembledContext(chunks=chunks, quality=quality)


async def complete_insight(
    uow_factory: InsightWorkUnitFactory,
    *,
    insight_id: InsightId,
    user_id: UserId,
    ai_response: InsightResponse,
    context_quality: ContextQuality,
    period_year: int,
    period_month: int,
) -> None:
    """TX4: aggregate budget snapshot + mark_completed + save.

    Raises `InsightNotFoundError` if the row disappeared between claim and save —
    treated as terminal failure by the caller.
    """
    with tracer.start_as_current_span("budget_summary_snapshot"):
        async with uow_factory() as uow:
            period_rows = await uow.budget_reader.read_month(
                user_id=user_id, year=period_year, month=period_month
            )
            budget_snapshot = BudgetSummarySnapshot.aggregate_rows(period_rows)  # type: ignore[arg-type]

            # Re-load inside this UoW so merge() updates the same row. Claim TX1
            # already committed status=PROCESSING durably, so the invariant
            # required by mark_completed holds.
            fresh = await uow.insight_repo.get_by_id(insight_id, user_id)
            if fresh is None:
                raise InsightNotFoundError(str(insight_id))

            fresh.mark_completed(
                title=ai_response.title,
                description=ai_response.description,
                impact_score=ai_response.impact_score,
                context_quality=context_quality,
                generated_at=datetime.now(UTC),
                budget_summary=budget_snapshot,
            )
            await uow.insight_repo.save(fresh)


async def record_failure(
    uow_factory: InsightWorkUnitFactory,
    *,
    insight_id: InsightId,
    user_id: UserId,
    error: str,
) -> None:
    """TX5: separate UoW so the FAILED row persists even if TX4 poisoned its session.

    Best-effort. If the FAILED persist itself fails, log and swallow so the
    original exception surfaces to the caller intact.
    """
    try:
        async with uow_factory() as uow:
            fresh = await uow.insight_repo.get_by_id(insight_id, user_id)
            if fresh is None:
                return
            fresh.mark_failed(error)
            await uow.insight_repo.save(fresh)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("process_insight_failure_persist_error", insight_id=str(insight_id))
