from dataclasses import dataclass
from typing import Any

from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.ports.work_unit import ChatWorkUnitFactory
from app.application.common.context_quality import assess_quality
from app.application.common.ports.chunk_retriever import RetrievedChunk
from app.application.common.ports.text_embedder import TextEmbedder
from app.domain.value_objects.enums import ContextQuality
from app.domain.value_objects.ids import UserId

HISTORY_TURNS = 5
MONTHLY_TOP_K = 2
SHIFT_TOP_K = 2


@dataclass(frozen=True, slots=True)
class ChatContext:
    chunks: list[RetrievedChunk]
    history: list[ChatTurn]
    context_quality: ContextQuality


async def retrieve_context(
    user_id: UserId,
    message: str,
    embedder: TextEmbedder,
    uow_factory: ChatWorkUnitFactory,
) -> ChatContext:
    """Embed query (no TX) → read chunks + history in one short TX → assess.

    No DB connection is held across the embedder call; the read TX is committed
    and the connection returned to the pool before the caller starts the LLM call.
    """
    query_embedding = await embedder.embed(message)

    async with uow_factory() as uow:
        chunks = await uow.chunk_retriever.search(
            user_id=user_id,
            query_embedding=query_embedding,
            monthly_top_k=MONTHLY_TOP_K,
            shift_top_k=SHIFT_TOP_K,
        )
        portrait = await uow.chunk_retriever.get_portrait(user_id)
        history = await uow.history_store.last_n(user_id, n=HISTORY_TURNS)

    if portrait:
        chunks = [portrait, *chunks]

    return ChatContext(
        chunks=chunks,
        history=history,
        context_quality=assess_quality(chunks),
    )


def chunks_metadata(chunks: list[RetrievedChunk]) -> tuple[dict[str, Any], ...]:
    return tuple({"chunk_type": c.chunk_type, "period_label": c.period_label} for c in chunks)
