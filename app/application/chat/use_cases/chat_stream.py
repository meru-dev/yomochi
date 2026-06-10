from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from app.application.chat._retrieval import chunks_metadata, retrieve_context
from app.application.chat.ports.chat_ai_client import (
    ChatAIClient,
    ChatRequest,
    StreamUsage,
)
from app.application.chat.ports.chat_history_store import ChatHistoryStore, ChatTurn
from app.application.chat.ports.chat_token_budget import ChatTokenBudget
from app.application.chat.ports.id_generator import ChatTurnIdGenerator
from app.application.common.ports.chunk_retriever import ChunkRetriever
from app.application.common.ports.text_embedder import TextEmbedder
from app.domain.value_objects.ids import UserId

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChatQueryCommand:
    user_id: UserId
    message: str


@dataclass(frozen=True, slots=True)
class ChatStreamDone:
    turn_id: str
    context_quality: str
    created_at: str


class ChatStreamUseCase:
    def __init__(
        self,
        chunk_retriever: ChunkRetriever,
        embedder: TextEmbedder,
        ai_client: ChatAIClient,
        history_store: ChatHistoryStore,
        token_budget: ChatTokenBudget,
        id_generator: ChatTurnIdGenerator,
    ) -> None:
        self._retriever = chunk_retriever
        self._embedder = embedder
        self._ai_client = ai_client
        self._store = history_store
        self._budget = token_budget
        self._id_gen = id_generator

    async def __call__(self, command: ChatQueryCommand) -> AsyncGenerator[str | ChatStreamDone]:
        user_id = command.user_id
        await self._budget.check(user_id)

        ctx = await retrieve_context(
            user_id, command.message, self._embedder, self._retriever, self._store
        )

        now = datetime.now(UTC)
        user_turn = ChatTurn(
            id=self._id_gen(),
            user_id=user_id,
            role="user",
            content=command.message,
            chunks_used=(),
            created_at=now,
        )
        assistant_id = self._id_gen()
        full_answer: list[str] = []
        assistant_created_at = now
        usage_tokens = 0

        try:
            async for item in self._ai_client.stream(
                ChatRequest(message=command.message, chunks=ctx.chunks, history=ctx.history)
            ):
                if isinstance(item, StreamUsage):
                    usage_tokens = item.prompt_tokens + item.completion_tokens
                else:
                    full_answer.append(item)
                    yield item
        finally:
            if usage_tokens > 0:
                try:
                    await self._budget.record(user_id, usage_tokens)
                except Exception:
                    logger.exception("chat_stream_budget_record_failed", user_id=str(user_id))

            answer = "".join(full_answer)
            if answer:
                assistant_turn = ChatTurn(
                    id=assistant_id,
                    user_id=user_id,
                    role="assistant",
                    content=answer,
                    chunks_used=chunks_metadata(ctx.chunks),
                    created_at=now,
                )
                try:
                    _, persisted = await self._store.append_turn_pair(
                        user_id, user_turn, assistant_turn
                    )
                    assistant_created_at = persisted.created_at
                except Exception:
                    logger.exception("chat_stream_save_failed", user_id=str(user_id))

        yield ChatStreamDone(
            turn_id=str(assistant_id),
            context_quality=ctx.context_quality.value,
            created_at=assistant_created_at.isoformat(),
        )
