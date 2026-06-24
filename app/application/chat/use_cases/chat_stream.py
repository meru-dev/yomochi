from collections.abc import AsyncGenerator
from dataclasses import dataclass

import structlog

from app.application.chat._tools_executor import build_tool_executor, tools_metadata
from app.application.chat.ports.chat_ai_client import (
    ChatAIClient,
    ChatToolsRequest,
    StreamUsage,
)
from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.ports.chat_token_budget import ChatTokenBudget
from app.application.chat.ports.chat_tools import ChatTools
from app.application.chat.ports.id_generator import ChatTurnIdGenerator
from app.application.chat.ports.work_unit import ChatWorkUnitFactory
from app.application.common.ports.clock import Clock
from app.domain.value_objects.ids import UserId

logger = structlog.get_logger(__name__)

# Number of prior turns loaded as chat history for the function-calling loop.
HISTORY_TURNS = 5

# Coarse chars-per-token heuristic, used only on the disconnect / no-usage path
# where the provider never delivered an exact usage chunk. Matches the ~4
# chars-per-token rule of thumb used elsewhere for English-ish text.
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class ChatQueryCommand:
    user_id: UserId
    message: str


@dataclass(frozen=True, slots=True)
class ChatStreamDone:
    turn_id: str
    context_quality: str
    created_at: str


def estimate_tokens_from_text(message: str, history: list[ChatTurn], answer: str) -> int:
    """Char-count token estimate for the tools path (no chunks).

    Pure fallback for when the AI client never yields a StreamUsage sentinel
    (e.g. the SSE client disconnected mid-stream). Counts the user message,
    prior history, and the partial answer produced so far. Always returns at
    least 1 so a started stream is never billed as free.
    """
    prompt_chars = len(message)
    prompt_chars += sum(len(turn.content) for turn in history)
    return (prompt_chars + len(answer)) // _CHARS_PER_TOKEN + 1


class ChatStreamUseCase:
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

    async def __call__(self, command: ChatQueryCommand) -> AsyncGenerator[str | ChatStreamDone]:
        """Streaming function-calling path: tool rounds resolved, final answer streamed."""
        user_id = command.user_id
        await self._budget.check(user_id)

        # TX1 (read) — history only; released before the LLM loop.
        async with self._uow_factory() as uow:
            history = await uow.history_store.last_n(user_id, n=HISTORY_TURNS)

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
        tools_used: tuple[str, ...] = ()
        tool_executor = build_tool_executor(self._chat_tools, user_id)
        request = ChatToolsRequest(
            message=command.message,
            history=history,
            tool_executor=tool_executor,
            today=self._clock.now().date(),
            cache_key=str(user_id),
        )

        try:
            async for item in self._ai_client.stream_with_tools(request):
                if isinstance(item, StreamUsage):
                    # The adapter may emit an early floor sentinel (tool-round
                    # tokens) before streaming, then a final one with the full
                    # total — both carry tools_used. Keeping the latest value
                    # means the normal path bills the final total once; on a
                    # disconnect the early floor is what survives.
                    usage_tokens = item.prompt_tokens + item.completion_tokens
                    tools_used = item.tools_used
                else:
                    full_answer.append(item)
                    yield item
        finally:
            answer = "".join(full_answer)

            tokens_to_record = usage_tokens
            if usage_tokens == 0 and answer:
                tokens_to_record = estimate_tokens_from_text(command.message, history, answer)
                logger.info("chat_stream_usage_estimated", estimated_tokens=tokens_to_record)

            if tokens_to_record > 0:
                try:
                    await self._budget.record(user_id, tokens_to_record)
                except Exception:
                    logger.exception("chat_stream_budget_record_failed", user_id=str(user_id))

            if answer:
                assistant_turn = ChatTurn(
                    id=assistant_id,
                    user_id=user_id,
                    role="assistant",
                    content=answer,
                    chunks_used=tools_metadata(tools_used),
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
            context_quality="full",
            created_at=assistant_created_at.isoformat(),
        )
