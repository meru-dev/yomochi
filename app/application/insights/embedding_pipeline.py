import structlog
from opentelemetry import trace

from app.application.common.ports.text_embedder import TextEmbedder
from app.application.insights.ports.alert_writer import AlertWriter
from app.application.insights.ports.budget_summary_reader import BudgetSummaryReader
from app.application.insights.ports.chunk_writer import ChunkToWrite, ChunkWriter
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector, format_shift_text
from app.domain.services.monthly_aggregator import (
    MonthlyAggregation,
    TransactionRow,
    aggregate,
    compute_semantic_hash,
    format_monthly_summary,
)
from app.domain.value_objects.ids import UserId

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_N_HISTORY_MONTHS = 3


class EmbeddingPipeline:
    def __init__(
        self,
        budget_reader: BudgetSummaryReader,
        chunk_writer: ChunkWriter,
        embedder: TextEmbedder,
        shift_detector: BehavioralShiftDetector | None = None,
        alert_writer: AlertWriter | None = None,
    ) -> None:
        self._budget = budget_reader
        self._writer = chunk_writer
        self._embedder = embedder
        self._detector = shift_detector or BehavioralShiftDetector()
        self._alert_writer = alert_writer

    async def refresh(self, user_id: UserId, year: int, month: int) -> None:
        with tracer.start_as_current_span("refresh_chunks") as span:
            span.set_attribute("user_id", str(user_id))
            span.set_attribute("period", f"{year}-{month:02d}")

            current_rows = await self._budget.read_month(user_id, year, month)
            if not current_rows:
                logger.info(
                    "embedding_pipeline_no_data", user_id=str(user_id), year=year, month=month
                )
                return

            current_aggs = aggregate(
                year,
                month,
                [
                    TransactionRow(
                        amount=r.amount,
                        currency=r.currency,
                        type_=r.type_,
                        category_label=r.category_label,
                        day_of_month=r.day_of_month,
                    )
                    for r in current_rows
                ],
            )

            history_raw = await self._budget.read_history_months(
                user_id, year, month, _N_HISTORY_MONTHS
            )
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

            await self._write_monthly_chunk(user_id, year, month, current_aggs)
            await self._write_shift_chunk(user_id, year, month, current_aggs, history_aggs)

    async def _write_monthly_chunk(
        self, user_id: UserId, year: int, month: int, aggs: list[MonthlyAggregation]
    ) -> None:
        content = format_monthly_summary(aggs)
        semantic_hash = compute_semantic_hash(aggs)

        with tracer.start_as_current_span("embed_query"):
            embedding = await self._embedder.embed(content)

        await self._writer.upsert(
            ChunkToWrite(
                user_id=user_id,
                chunk_type="monthly_summary",
                period_year=year,
                period_month=month,
                content=content,
                embedding=embedding,
                semantic_hash=semantic_hash,
                metadata={"year": year, "month": month},
            )
        )

    async def _write_shift_chunk(
        self,
        user_id: UserId,
        year: int,
        month: int,
        current_aggs: list[MonthlyAggregation],
        history_aggs: list[MonthlyAggregation],
    ) -> None:
        if not current_aggs or len(history_aggs) < 2:
            return

        primary = current_aggs[0]
        same_currency_history = [h for h in history_aggs if h.currency == primary.currency]
        shifts = self._detector.detect(primary, same_currency_history)
        if not shifts:
            return

        content = format_shift_text(primary, shifts)
        semantic_hash = compute_semantic_hash(current_aggs, bucket_pct=0.10)
        metadata = {"year": year, "month": month, "shifts": [s.to_metadata() for s in shifts]}

        with tracer.start_as_current_span("embed_shift"):
            embedding = await self._embedder.embed(content)

        await self._writer.upsert(
            ChunkToWrite(
                user_id=user_id,
                chunk_type="behavioral_shift",
                period_year=year,
                period_month=month,
                content=content,
                embedding=embedding,
                semantic_hash=semantic_hash,
                metadata=metadata,
            )
        )

        if self._alert_writer and shifts:
            await self._alert_writer.write_shift_alerts(user_id, year, month, shifts)
