from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol

from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.common.ports.chunk_retriever import RetrievedChunk


@dataclass(frozen=True)
class ChatRequest:
    message: str
    chunks: list[RetrievedChunk]
    history: list[ChatTurn]


@dataclass(frozen=True)
class ChatResponse:
    answer: str
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class StreamUsage:
    prompt_tokens: int
    completion_tokens: int


class ChatAIClient(Protocol):
    async def chat(self, request: ChatRequest) -> ChatResponse: ...
    def stream(self, request: ChatRequest) -> AsyncGenerator[str | StreamUsage]: ...
