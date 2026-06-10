import os
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest

from app.application.chat.ports.chat_ai_client import (
    ChatRequest,
    ChatResponse,
)
from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.use_cases.chat_stream import ChatStreamDone, ChatStreamUseCase
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.system.uuid7_id_generator import Uuid7ChatTurnIdGenerator

_ID_GEN = Uuid7ChatTurnIdGenerator()


class FakeChatTokenBudget:
    def __init__(self) -> None:
        self.checks: int = 0
        self.recorded: list[int] = []

    async def check(self, user_id) -> None:
        self.checks += 1

    async def record(self, user_id, tokens: int) -> None:
        self.recorded.append(tokens)


class FakeStreamingClient:
    def __init__(self, tokens: list[str]):
        self._tokens = tokens

    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(answer="", prompt_tokens=0, completion_tokens=0)

    async def stream(self, request: ChatRequest) -> AsyncGenerator[str]:
        for t in self._tokens:
            yield t


class FakeChatHistoryStore:
    def __init__(self):
        self.saved: list[ChatTurn] = []
        self.history: list[ChatTurn] = []

    async def last_n(self, user_id: UserId, n: int) -> list[ChatTurn]:
        return self.history[-n:]

    async def save_turns(self, user_id: UserId, turns: list[ChatTurn]) -> None:
        self.saved.extend(turns)

    async def append_turn_pair(self, user_id, user_turn, assistant_turn):
        self.saved.extend([user_turn, assistant_turn])
        return user_turn, assistant_turn

    async def list_for_user(self, user_id, limit, cursor):
        return []

    async def clear_all(self, user_id):
        self.saved.clear()


class FakeChunkRetriever:
    async def search(self, user_id, query_embedding, monthly_top_k=3, shift_top_k=2):
        return []

    async def get_portrait(self, user_id):
        return None


class FakeTextEmbedder:
    async def embed(self, text: str) -> list[float]:
        return [0.1, 0.2]


@pytest.mark.asyncio
async def test_stream_yields_tokens_then_done():
    store = FakeChatHistoryStore()
    uc = ChatStreamUseCase(
        chunk_retriever=FakeChunkRetriever(),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClient(["Hello", " world"]),
        history_store=store,
        token_budget=FakeChatTokenBudget(),
        id_generator=_ID_GEN,
    )
    from app.application.chat.use_cases.chat_stream import ChatQueryCommand

    items = []
    async for item in uc(ChatQueryCommand(user_id=UserId(uuid.uuid4()), message="test")):
        items.append(item)

    tokens = [i for i in items if isinstance(i, str)]
    dones = [i for i in items if isinstance(i, ChatStreamDone)]

    assert tokens == ["Hello", " world"]
    assert len(dones) == 1
    assert dones[0].context_quality == "none"


@pytest.mark.asyncio
async def test_stream_saves_both_turns():
    store = FakeChatHistoryStore()
    uc = ChatStreamUseCase(
        chunk_retriever=FakeChunkRetriever(),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClient(["Hi", "!"]),
        history_store=store,
        token_budget=FakeChatTokenBudget(),
        id_generator=_ID_GEN,
    )
    from app.application.chat.use_cases.chat_stream import ChatQueryCommand

    async for _ in uc(ChatQueryCommand(user_id=UserId(uuid.uuid4()), message="hey")):
        pass

    assert len(store.saved) == 2
    assert store.saved[0].role == "user"
    assert store.saved[1].role == "assistant"
    assert store.saved[1].content == "Hi!"


@pytest.mark.asyncio
@pytest.mark.skipif(
    bool(os.environ.get("MUTANT_UNDER_TEST")),
    reason="mutmut async-generator wrapper drops GeneratorExit propagation",
)
async def test_stream_saves_partial_on_early_close():
    """Even if generator is closed early, collected tokens are saved."""
    store = FakeChatHistoryStore()
    uc = ChatStreamUseCase(
        chunk_retriever=FakeChunkRetriever(),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClient(["tok1", "tok2", "tok3"]),
        history_store=store,
        token_budget=FakeChatTokenBudget(),
        id_generator=_ID_GEN,
    )
    from app.application.chat.use_cases.chat_stream import ChatQueryCommand

    gen = uc(ChatQueryCommand(user_id=UserId(uuid.uuid4()), message="q"))
    await gen.__anext__()  # get "tok1"
    await gen.__anext__()  # get "tok2"
    await gen.aclose()  # close early

    # user turn + partial assistant turn should be saved
    assert len(store.saved) == 2
    assert store.saved[1].content == "tok1tok2"


@pytest.mark.asyncio
async def test_chat_stream_turn_ids_are_uuid7() -> None:
    """Turn IDs written to the history store must be uuid7 (version 7)."""
    from app.application.chat.ports.chat_ai_client import StreamUsage
    from app.application.chat.use_cases.chat_stream import ChatQueryCommand, ChatStreamUseCase
    from app.domain.value_objects.ids import UserId

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.0] * 1536)

    retriever = AsyncMock()
    retriever.search = AsyncMock(return_value=[])
    retriever.get_portrait = AsyncMock(return_value=None)

    captured_turns: list = []

    async def _append(user_id, user_turn, assistant_turn):
        captured_turns.extend([user_turn, assistant_turn])
        return user_turn, assistant_turn

    history_store = AsyncMock()
    history_store.last_n = AsyncMock(return_value=[])
    history_store.append_turn_pair = AsyncMock(side_effect=_append)

    budget = AsyncMock()
    budget.check = AsyncMock()
    budget.record = AsyncMock()

    ai_client = AsyncMock()

    async def _stream(_req):
        yield "hello"
        yield StreamUsage(prompt_tokens=10, completion_tokens=5)

    ai_client.stream = _stream

    uc = ChatStreamUseCase(
        chunk_retriever=retriever,
        embedder=embedder,
        ai_client=ai_client,
        history_store=history_store,
        token_budget=budget,
        id_generator=_ID_GEN,
    )

    user_id = UserId(uuid.uuid4())
    [item async for item in uc(ChatQueryCommand(user_id=user_id, message="hi"))]

    assert len(captured_turns) == 2
    for turn in captured_turns:
        assert turn.id.version == 7, f"expected uuid7, got version {turn.id.version}"
