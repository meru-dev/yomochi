from datetime import UTC, datetime
from typing import Any

import structlog

from app.application.common.ports.text_embedder import TextEmbedder
from app.application.insights.ports.budget_summary_reader import BudgetSummaryReader
from app.application.insights.ports.chunk_writer import ChunkToWrite, ChunkWriter
from app.domain.services.monthly_aggregator import (
    TransactionRow,
    aggregate,
    compute_semantic_hash,
)
from app.domain.services.portrait_aggregator import format_portrait_text
from app.domain.value_objects.ids import UserId

logger = structlog.get_logger(__name__)

_N_HISTORY_MONTHS = 4


class PortraitPipeline:
    def __init__(
        self,
        budget_reader: BudgetSummaryReader,
        chunk_writer: ChunkWriter,
        embedder: TextEmbedder,
    ) -> None:
        self._budget = budget_reader
        self._writer = chunk_writer
        self._embedder = embedder

    async def refresh(self, user_id: UserId) -> None:
        today = datetime.now(UTC).date()
        raw = await self._budget.read_history_months(
            user_id, today.year, today.month, n_months=_N_HISTORY_MONTHS
        )

        sorted_months = sorted(raw.items())
        if len(sorted_months) < 2:
            return

        (ry, rm), rrows = sorted_months[-1]
        if not rrows:
            return

        recent_agg = aggregate(ry, rm, [_to_row(r) for r in rrows])
        baseline_aggs = [
            aggregate(y, m, [_to_row(r) for r in rows])
            for (y, m), rows in sorted_months[:-1]
            if rows
        ]

        content = format_portrait_text(recent_agg, baseline_aggs)
        all_aggs = recent_agg + [a for month in baseline_aggs for a in month]
        semantic_hash = compute_semantic_hash(all_aggs)

        embedding = await self._embedder.embed(content)

        await self._writer.upsert(
            ChunkToWrite(
                user_id=user_id,
                chunk_type="user_portrait",
                period_year=0,
                period_month=0,
                content=content,
                embedding=embedding,
                semantic_hash=semantic_hash,
                metadata={
                    "recent_year": ry,
                    "recent_month": rm,
                    "baseline_months": len(baseline_aggs),
                },
            )
        )
        logger.info("portrait_refreshed", user_id=str(user_id), recent_year=ry, recent_month=rm)


def _to_row(r: Any) -> TransactionRow:
    return TransactionRow(
        amount=r.amount,
        currency=r.currency,
        type_=r.type_,
        category_label=r.category_label,
        day_of_month=r.day_of_month,
    )
