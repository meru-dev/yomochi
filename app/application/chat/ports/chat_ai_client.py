from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.application.chat.ports.chat_history_store import ChatTurn

# A tool executor is an async callable supplied by the use case. It closes over
# the injected ChatTools impl and the request user_id, dispatches by tool name,
# and returns a json-serialisable dict (already passed through to_jsonable).
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ChatToolsRequest:
    message: str
    history: list[ChatTurn]
    tool_executor: ToolExecutor
    today: date | None = None
    # Stable per-user key the AI adapter MAY use for provider-side cache routing
    # provider-neutral; the OpenAI adapter maps it to prompt_cache_key.
    cache_key: str | None = None


@dataclass(frozen=True)
class ChatResponse:
    answer: str
    prompt_tokens: int
    completion_tokens: int
    # Tool names invoked across all rounds, in call order.
    tools_used: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StreamUsage:
    prompt_tokens: int
    completion_tokens: int
    # Tool names invoked across all rounds, in call order. Carried on the
    # sentinel so the streamed assistant turn can record the same tool
    # provenance as the non-streamed path.
    tools_used: tuple[str, ...] = field(default_factory=tuple)


class ChatAIClient(Protocol):
    async def chat_with_tools(self, request: ChatToolsRequest) -> ChatResponse: ...
    def stream_with_tools(self, request: ChatToolsRequest) -> AsyncGenerator[str | StreamUsage]: ...
