from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.chat._retrieval import chunks_metadata, retrieve_context
from app.application.chat.ports.chat_ai_client import ChatAIClient, ChatRequest
from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.ports.chat_token_budget import ChatTokenBudget
from app.application.chat.ports.id_generator import ChatTurnIdGenerator
from app.application.chat.ports.work_unit import ChatWorkUnitFactory
from app.application.common.ports.clock import Clock
from app.application.common.ports.text_embedder import TextEmbedder
from app.domain.value_objects.enums import ContextQuality
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class ChatQueryCommand:
    user_id: UserId
    message: str


@dataclass(frozen=True, slots=True)
class ChatQueryResult:
    turn_id: UUID
    answer: str
    context_quality: ContextQuality
    created_at: datetime


class ChatQueryUseCase:
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

    async def __call__(self, command: ChatQueryCommand) -> ChatQueryResult:
        await self._budget.check(command.user_id)

        # User turn is stamped when request handling begins.
        user_created_at = self._clock.now()

        # TX1 (read) — committed/released before the embedder + LLM calls below.
        ctx = await retrieve_context(
            command.user_id, command.message, self._embedder, self._uow_factory
        )

        # No session checked out across the LLM call.
        ai_response = await self._ai_client.chat(
            ChatRequest(message=command.message, chunks=ctx.chunks, history=ctx.history)
        )
        await self._budget.record(
            command.user_id, ai_response.prompt_tokens + ai_response.completion_tokens
        )

        user_turn = ChatTurn(
            id=self._id_gen(),
            user_id=command.user_id,
            role="user",
            content=command.message,
            chunks_used=(),
            created_at=user_created_at,
        )
        # Assistant turn is stamped at construction time, after the LLM reply.
        # The µs-resolution system clock makes this strictly later in practice;
        # a tie is broken by the monotone UUID7 ids from the same generator.
        assistant_turn = ChatTurn(
            id=self._id_gen(),
            user_id=command.user_id,
            role="assistant",
            content=ai_response.answer,
            chunks_used=chunks_metadata(ctx.chunks),
            created_at=self._clock.now(),
        )
        # TX2 (write) — fresh short TX after the LLM call.
        async with self._uow_factory() as uow:
            _, persisted_assistant = await uow.history_store.append_turn_pair(
                command.user_id, user_turn, assistant_turn
            )

        return ChatQueryResult(
            turn_id=persisted_assistant.id,
            answer=ai_response.answer,
            context_quality=ctx.context_quality,
            created_at=persisted_assistant.created_at,
        )
