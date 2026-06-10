from unittest.mock import AsyncMock, MagicMock

import pytest
import uuid_utils as uuid

from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.insights.chunk_retriever import SqlaChunkRetriever

pytestmark = pytest.mark.asyncio


def _embedding(n: int = 1536) -> list[float]:
    return [0.123456789] * n


async def test_search_binds_embedding_as_parameter_and_does_not_inline_it() -> None:
    """Embedding must appear in the bound params, never in the SQL text."""
    session = AsyncMock()
    empty_result = MagicMock()
    empty_result.fetchall = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=empty_result)

    retriever = SqlaChunkRetriever(session)
    emb = _embedding()
    await retriever.search(user_id=UserId(uuid.uuid7()), query_embedding=emb)

    inline_signature = "[0.123456789,"
    saw_embedding_param = False
    for call in session.execute.await_args_list:
        stmt = call.args[0]
        sql_text = str(stmt)
        assert inline_signature not in sql_text, (
            "embedding interpolated into SQL — must be bound as :embedding parameter"
        )
        # Bound params live in call.args[1] for the two retrieval queries.
        if len(call.args) > 1 and isinstance(call.args[1], dict):
            params = call.args[1]
            if "embedding" in params:
                saw_embedding_param = True
                # The value can be a list (registered Vector type) or a "[v1,v2,...]" literal
                # bound + cast inside SQL — either is fine, both are bound params.
                assert params["embedding"] is not None

    assert saw_embedding_param, "expected at least one execute() to bind `embedding` parameter"


async def test_search_issues_one_execute_call() -> None:
    """After UNION ALL refactor, search() must fire exactly one execute (plus the SET LOCAL)."""
    session = AsyncMock()
    empty_result = MagicMock()
    empty_result.fetchall = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=empty_result)

    retriever = SqlaChunkRetriever(session)
    await retriever.search(user_id=UserId(uuid.uuid7()), query_embedding=[0.1] * 1536)

    # After engine-listener refactor: only 1 UNION ALL query (no SET LOCAL inline)
    assert session.execute.await_count == 1, (
        f"expected 1 execute() call (UNION ALL only), got {session.execute.await_count}"
    )


async def test_chunk_writer_binds_embedding_as_parameter() -> None:
    """The writer already binds :embedding; pin that contract so a future refactor doesn't regress."""
    from app.application.insights.ports.chunk_writer import ChunkToWrite
    from app.outbound.adapters.sqla.insights.chunk_writer import SqlaChunkWriter

    session = AsyncMock()
    session.execute = AsyncMock()
    writer = SqlaChunkWriter(session)

    chunk = ChunkToWrite(
        user_id=UserId(uuid.uuid7()),
        chunk_type="monthly_summary",
        period_year=2026,
        period_month=4,
        content="x",
        embedding=_embedding(),
        semantic_hash="abc",
        metadata={},
    )
    await writer.upsert(chunk)

    call = session.execute.await_args_list[0]
    sql_text = str(call.args[0])
    params = call.args[1]

    inline_signature = "[0.123456789,"
    assert inline_signature not in sql_text
    assert "embedding" in params
    assert params["embedding"] is not None
