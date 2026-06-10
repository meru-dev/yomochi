import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from opentelemetry import trace

from app.application.common.context_quality import assess_quality
from app.application.common.ports.chunk_retriever import RetrievedChunk
from app.application.common.ports.text_embedder import TextEmbedder
from app.application.insights.embedding_pipeline import EmbeddingPipeline
from app.application.insights.ports.ai_insight_client import InsightResponse
from app.application.insights.ports.insight_repository import InsightNotFoundError
from app.application.insights.ports.work_unit import InsightWorkUnitFactory
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
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
    chunks: list[RetrievedChunk]
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


async def assemble_context(
    uow_factory: InsightWorkUnitFactory,
    embedder: TextEmbedder,
    shift_detector: BehavioralShiftDetector,
    *,
    user_id: UserId,
    period_year: int,
    period_month: int,
) -> AssembledContext:
    """Refresh chunks (TX2) → embed query (no TX) → retrieve (TX3) → assess.

    No DB transaction is held across the embedder call; that's the whole point
    of the split. Returns the chunks the AI client will see plus the quality
    grade — callers short-circuit to failure on `ContextQuality.NONE`.
    """
    # TX2 — refresh
    with tracer.start_as_current_span("refresh_chunks"):
        async with uow_factory() as uow:
            pipeline = EmbeddingPipeline(
                budget_reader=uow.budget_reader,
                chunk_writer=uow.chunk_writer,
                embedder=embedder,
                shift_detector=shift_detector,
                alert_writer=uow.alert_writer,
            )
            await pipeline.refresh(user_id=user_id, year=period_year, month=period_month)

    # Embed query — pure network, no TX
    query_text = f"Financial insights for period {period_year}-{period_month:02d}"
    with tracer.start_as_current_span("embed_query"):
        query_embedding = await embedder.embed(query_text)

    # TX3 — read-only retrieve
    with tracer.start_as_current_span("rag_retrieve"):
        async with uow_factory() as uow:
            chunks = await uow.chunk_retriever.search(
                user_id=user_id, query_embedding=query_embedding
            )
            portrait = await uow.chunk_retriever.get_portrait(user_id)

    if portrait is not None:
        chunks = [portrait, *chunks]

    return AssembledContext(chunks=list(chunks), quality=assess_quality(chunks))


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
