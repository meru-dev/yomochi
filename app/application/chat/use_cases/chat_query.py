from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.chat._tools_executor import build_tool_executor, tools_metadata
from app.application.chat.ports.chat_ai_client import (
    ChatAIClient,
    ChatToolsRequest,
)
from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.ports.chat_token_budget import ChatTokenBudget
from app.application.chat.ports.chat_tools import ChatTools
from app.application.chat.ports.id_generator import ChatTurnIdGenerator
from app.application.chat.ports.work_unit import ChatWorkUnitFactory
from app.application.common.ports.clock import Clock
from app.domain.value_objects.enums import ContextQuality
from app.domain.value_objects.ids import UserId

# Number of prior turns loaded as chat history for the function-calling loop.
HISTORY_TURNS = 5


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
        ai_client: ChatAIClient,
        token_budget: ChatTokenBudget,
        id_generator: ChatTurnIdGenerator,
        clock: Clock,
        chat_tools: ChatTools,
    ) -> None:
        self._uow_factory = work_unit_factory
        self._ai_client = ai_client
        self._budget = token_budget
        self._id_gen = id_generator
        self._clock = clock
        self._chat_tools = chat_tools

    async def __call__(self, command: ChatQueryCommand) -> ChatQueryResult:
        await self._budget.check(command.user_id)

        # User turn is stamped when request handling begins.
        user_created_at = self._clock.now()

        # TX1 (read) — history only; released before the LLM loop.
        async with self._uow_factory() as uow:
            history = await uow.history_store.last_n(command.user_id, n=HISTORY_TURNS)

        tool_executor = build_tool_executor(self._chat_tools, command.user_id)
        ai_response = await self._ai_client.chat_with_tools(
            ChatToolsRequest(
                message=command.message,
                history=history,
                tool_executor=tool_executor,
                today=user_created_at.date(),
                cache_key=str(command.user_id),
            )
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
        # Assistant turn is stamped at construction time, after the LLM loop.
        # The µs-resolution system clock makes this strictly later in practice;
        # a tie is broken by the monotone UUID7 ids from the same generator.
        assistant_turn = ChatTurn(
            id=self._id_gen(),
            user_id=command.user_id,
            role="assistant",
            content=ai_response.answer,
            chunks_used=tools_metadata(ai_response.tools_used),
            created_at=self._clock.now(),
        )
        # TX2 (write) — fresh short TX after the LLM loop.
        async with self._uow_factory() as uow:
            _, persisted_assistant = await uow.history_store.append_turn_pair(
                command.user_id, user_turn, assistant_turn
            )

        return ChatQueryResult(
            turn_id=persisted_assistant.id,
            answer=ai_response.answer,
            context_quality=ContextQuality.FULL,
            created_at=persisted_assistant.created_at,
        )
