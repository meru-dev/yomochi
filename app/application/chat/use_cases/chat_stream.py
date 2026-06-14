from collections.abc import AsyncGenerator
from dataclasses import dataclass

import structlog

from app.application.chat._retrieval import chunks_metadata, retrieve_context
from app.application.chat.ports.chat_ai_client import (
    ChatAIClient,
    ChatRequest,
    StreamUsage,
)
from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.ports.chat_token_budget import ChatTokenBudget
from app.application.chat.ports.id_generator import ChatTurnIdGenerator
from app.application.chat.ports.work_unit import ChatWorkUnitFactory
from app.application.common.ports.clock import Clock
from app.application.common.ports.text_embedder import TextEmbedder
from app.domain.value_objects.ids import UserId

logger = structlog.get_logger(__name__)

# Coarse chars-per-token heuristic, used only on the disconnect / no-usage path
# where the provider never delivered an exact usage chunk. Matches the ~4
# chars-per-token rule of thumb used elsewhere for English-ish text.
_CHARS_PER_TOKEN = 4


def estimate_tokens(request: ChatRequest, answer: str) -> int:
    """Estimate total tokens (prompt + completion) from raw character counts.

    Pure fallback for when the AI client never yields a StreamUsage sentinel
    (e.g. the SSE client disconnected mid-stream). Counts the user message,
    retrieved context chunks, prior history, and the partial answer produced so
    far. Always returns at least 1 so a started stream is never billed as free.
    """
    prompt_chars = len(request.message)
    prompt_chars += sum(len(chunk.content) for chunk in request.chunks)
    prompt_chars += sum(len(turn.content) for turn in request.history)
    return (prompt_chars + len(answer)) // _CHARS_PER_TOKEN + 1


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
        work_unit_factory: ChatWorkUnitFactory,
        embedder: TextEmbedder,
        ai_client: ChatAIClient,
        token_budget: ChatTokenBudget,
        id_generator: ChatTurnIdGenerator,
        clock: Clock,
    ) -> None:
        self._uow_factory = work_unit_factory
        self._embedder = embedder
        self._ai_client = ai_client
        self._budget = token_budget
        self._id_gen = id_generator
        self._clock = clock

    async def __call__(self, command: ChatQueryCommand) -> AsyncGenerator[str | ChatStreamDone]:
        user_id = command.user_id
        await self._budget.check(user_id)

        # TX1 (read) — committed/released before streaming starts.
        ctx = await retrieve_context(user_id, command.message, self._embedder, self._uow_factory)

        # User turn is stamped when request handling begins.
        user_turn = ChatTurn(
            id=self._id_gen(),
            user_id=user_id,
            role="user",
            content=command.message,
            chunks_used=(),
            created_at=self._clock.now(),
        )
        assistant_id = self._id_gen()
        full_answer: list[str] = []
        assistant_created_at = user_turn.created_at
        usage_tokens = 0
        request = ChatRequest(message=command.message, chunks=ctx.chunks, history=ctx.history)

        try:
            # No session checked out while streaming from the LLM.
            async for item in self._ai_client.stream(request):
                if isinstance(item, StreamUsage):
                    usage_tokens = item.prompt_tokens + item.completion_tokens
                else:
                    full_answer.append(item)
                    yield item
        finally:
            answer = "".join(full_answer)

            # Exact usage is preferred. When the sentinel never arrived (client
            # disconnect / stream cut before the usage chunk) but the stream did
            # start, fall back to a char-count estimate so tokens aren't free.
            tokens_to_record = usage_tokens
            if usage_tokens == 0 and answer:
                tokens_to_record = estimate_tokens(request, answer)
                logger.info("chat_stream_usage_estimated", estimated_tokens=tokens_to_record)

            if tokens_to_record > 0:
                try:
                    await self._budget.record(user_id, tokens_to_record)
                except Exception:
                    logger.exception("chat_stream_budget_record_failed", user_id=str(user_id))

            if answer:
                # Assistant turn is stamped here, when the answer is assembled —
                # strictly after the user turn at µs resolution; ties broken by
                # the monotone UUID7 ids from the same generator.
                assistant_turn = ChatTurn(
                    id=assistant_id,
                    user_id=user_id,
                    role="assistant",
                    content=answer,
                    chunks_used=chunks_metadata(ctx.chunks),
                    created_at=self._clock.now(),
                )
                try:
                    # TX2 (write) — fresh short TX from the APP-scoped factory, which
                    # outlives the request scope (the SSE generator may run past it).
                    async with self._uow_factory() as uow:
                        _, persisted = await uow.history_store.append_turn_pair(
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
