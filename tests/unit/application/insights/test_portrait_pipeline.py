import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.insights.portrait_pipeline import PortraitPipeline
from app.application.insights.ports.budget_summary_reader import BudgetTransactionRow
from app.application.insights.ports.chunk_writer import ChunkToWrite
from app.domain.value_objects.ids import UserId

pytestmark = pytest.mark.asyncio

_UID = UserId(uuid.uuid4())
_EMBEDDING = [0.1] * 1536
_ROW = BudgetTransactionRow(
    amount=Decimal("5000"),
    currency="JPY",
    type_="expense",
    category_label="Food",
    day_of_month=10,
)


def _make_pipeline(embedder, reader, writer):
    return PortraitPipeline(budget_reader=reader, chunk_writer=writer, embedder=embedder)


async def test_refresh_skips_when_fewer_than_2_months():
    embedder = AsyncMock()
    reader = MagicMock()
    reader.read_history_months = AsyncMock(return_value={})
    writer = MagicMock()
    writer.upsert = AsyncMock()

    await _make_pipeline(embedder, reader, writer).refresh(_UID)

    embedder.embed.assert_not_called()
    writer.upsert.assert_not_called()


async def test_refresh_skips_when_recent_month_empty():
    embedder = AsyncMock()
    raw = {(2026, 2): [_ROW], (2026, 3): []}  # recent month (3) is empty
    reader = MagicMock()
    reader.read_history_months = AsyncMock(return_value=raw)
    writer = MagicMock()
    writer.upsert = AsyncMock()

    await _make_pipeline(embedder, reader, writer).refresh(_UID)

    embedder.embed.assert_not_called()
    writer.upsert.assert_not_called()


async def test_refresh_upserts_with_sentinel_period():
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=_EMBEDDING)
    raw = {
        (2026, 2): [_ROW],
        (2026, 3): [_ROW],
        (2026, 4): [_ROW],
        (2026, 5): [_ROW],
    }
    reader = MagicMock()
    reader.read_history_months = AsyncMock(return_value=raw)
    writer = MagicMock()
    writer.upsert = AsyncMock()

    await _make_pipeline(embedder, reader, writer).refresh(_UID)

    embedder.embed.assert_called_once()
    chunk: ChunkToWrite = writer.upsert.call_args[0][0]
    assert isinstance(chunk, ChunkToWrite)
    assert chunk.chunk_type == "user_portrait"
    assert chunk.period_year == 0
    assert chunk.period_month == 0
    assert chunk.user_id == _UID
    assert len(chunk.embedding) == 1536
