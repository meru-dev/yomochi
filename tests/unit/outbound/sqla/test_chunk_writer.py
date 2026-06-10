from unittest.mock import AsyncMock

import pytest
import uuid_utils as uuid

from app.application.insights.ports.chunk_writer import ChunkToWrite
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.insights.chunk_writer import SqlaChunkWriter


def _make_chunk(embedding: list[float]) -> ChunkToWrite:
    return ChunkToWrite(
        user_id=UserId(uuid.uuid7()),
        chunk_type="monthly_summary",
        period_year=2025,
        period_month=1,
        content="Some content",
        embedding=embedding,
        semantic_hash="abc123",
        metadata={},
    )


@pytest.mark.asyncio
async def test_chunk_writer_rejects_wrong_dimension():
    session = AsyncMock()
    writer = SqlaChunkWriter(session)
    chunk = _make_chunk(embedding=[0.1] * 512)
    with pytest.raises(ValueError, match="1536"):
        await writer.upsert(chunk)


@pytest.mark.asyncio
async def test_chunk_writer_accepts_correct_dimension():
    session = AsyncMock()
    session.execute = AsyncMock()
    writer = SqlaChunkWriter(session)
    chunk = _make_chunk(embedding=[0.1] * 1536)
    await writer.upsert(chunk)
    session.execute.assert_awaited_once()
