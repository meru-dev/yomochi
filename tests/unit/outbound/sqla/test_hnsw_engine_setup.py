from unittest.mock import AsyncMock, MagicMock

import pytest

from app.outbound.adapters.sqla.insights.chunk_retriever import SqlaChunkRetriever


@pytest.mark.asyncio
async def test_search_does_not_set_hnsw_inline() -> None:
    """After the engine-listener refactor, search() must NOT call SET LOCAL hnsw.ef_search."""
    session = AsyncMock()
    empty_result = MagicMock()
    empty_result.fetchall = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=empty_result)

    import uuid_utils as uuid

    from app.domain.value_objects.ids import UserId

    retriever = SqlaChunkRetriever(session)
    await retriever.search(user_id=UserId(uuid.uuid7()), query_embedding=[0.1] * 1536)

    for call in session.execute.await_args_list:
        stmt_text = str(call.args[0]).lower()
        assert "hnsw" not in stmt_text, (
            "hnsw.ef_search must be set via engine connect listener, not inline SQL"
        )
