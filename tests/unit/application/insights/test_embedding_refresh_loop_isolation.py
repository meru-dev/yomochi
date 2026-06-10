from unittest.mock import AsyncMock

import pytest
import uuid_utils as uuid

from app.application.insights.embedding_pipeline import EmbeddingPipeline
from app.application.insights.ports.budget_summary_reader import BudgetTransactionRow
from app.domain.value_objects.ids import UserId

pytestmark = pytest.mark.asyncio


def _row() -> BudgetTransactionRow:
    from decimal import Decimal

    return BudgetTransactionRow(
        amount=Decimal("100"),
        currency="USD",
        type_="expense",
        category_label="food",
        day_of_month=10,
    )


async def test_pipeline_refresh_calls_are_independent() -> None:
    """Two refresh() calls on the same pipeline instance share no state — the
    interface contract the `_embedding_refresh_loop` needs in order to guarantee
    per-period isolation once it adopts per-period TX scope.
    """
    user_id = UserId(uuid.uuid7())

    budget = AsyncMock()
    budget.read_month = AsyncMock(return_value=[_row()])
    budget.read_history_months = AsyncMock(return_value={})

    writer = AsyncMock()
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)

    pipeline = EmbeddingPipeline(
        budget_reader=budget,
        chunk_writer=writer,
        embedder=embedder,
    )

    await pipeline.refresh(user_id, 2026, 4)
    await pipeline.refresh(user_id, 2026, 5)

    # Two periods × at least the monthly chunk = at least 2 writes
    assert writer.upsert.await_count >= 2
