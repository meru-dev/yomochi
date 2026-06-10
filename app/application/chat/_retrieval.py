from dataclasses import dataclass
from typing import Any

from app.application.chat.ports.chat_history_store import ChatHistoryStore, ChatTurn
from app.application.common.context_quality import assess_quality
from app.application.common.ports.chunk_retriever import ChunkRetriever, RetrievedChunk
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
    retriever: ChunkRetriever,
    history_store: ChatHistoryStore,
) -> ChatContext:
    query_embedding = await embedder.embed(message)
    chunks = await retriever.search(
        user_id=user_id,
        query_embedding=query_embedding,
        monthly_top_k=MONTHLY_TOP_K,
        shift_top_k=SHIFT_TOP_K,
    )
    portrait = await retriever.get_portrait(user_id)
    if portrait:
        chunks = [portrait, *chunks]
    history = await history_store.last_n(user_id, n=HISTORY_TURNS)
    return ChatContext(
        chunks=chunks,
        history=history,
        context_quality=assess_quality(chunks),
    )


def chunks_metadata(chunks: list[RetrievedChunk]) -> tuple[dict[str, Any], ...]:
    return tuple({"chunk_type": c.chunk_type, "period_label": c.period_label} for c in chunks)
