import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.chat.ports.chat_ai_client import (
    ChatRequest,
    ChatResponse,
    StreamUsage,
)
from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.ports.work_unit import ChatWorkUnit
from app.application.chat.use_cases.chat_stream import (
    ChatStreamDone,
    ChatStreamUseCase,
    estimate_tokens,
)
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.system.uuid7_id_generator import Uuid7ChatTurnIdGenerator

_ID_GEN = Uuid7ChatTurnIdGenerator()


class FixedClock:
    """Clock returning a constant instant; forces id-based tiebreak in tests."""

    def __init__(self, instant: datetime | None = None) -> None:
        self._instant = instant or datetime(2026, 6, 12, tzinfo=UTC)

    def now(self) -> datetime:
        return self._instant

    def today(self):
        return self._instant.date()


class FakeChatWorkUnitFactory:
    """Hands out a UoW bundling the given retriever + store."""

    def __init__(self, retriever, store) -> None:
        self._uow = ChatWorkUnit(chunk_retriever=retriever, history_store=store)

    def __call__(self):
        @asynccontextmanager
        async def _scope():
            yield self._uow

        return _scope()


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
        work_unit_factory=FakeChatWorkUnitFactory(FakeChunkRetriever(), store),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClient(["Hello", " world"]),
        token_budget=FakeChatTokenBudget(),
        id_generator=_ID_GEN,
        clock=FixedClock(),
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
        work_unit_factory=FakeChatWorkUnitFactory(FakeChunkRetriever(), store),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClient(["Hi", "!"]),
        token_budget=FakeChatTokenBudget(),
        id_generator=_ID_GEN,
        clock=FixedClock(),
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
        work_unit_factory=FakeChatWorkUnitFactory(FakeChunkRetriever(), store),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClient(["tok1", "tok2", "tok3"]),
        token_budget=FakeChatTokenBudget(),
        id_generator=_ID_GEN,
        clock=FixedClock(),
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
        work_unit_factory=FakeChatWorkUnitFactory(retriever, history_store),
        embedder=embedder,
        ai_client=ai_client,
        token_budget=budget,
        id_generator=_ID_GEN,
        clock=FixedClock(),
    )

    user_id = UserId(uuid.uuid4())
    [item async for item in uc(ChatQueryCommand(user_id=user_id, message="hi"))]

    assert len(captured_turns) == 2
    for turn in captured_turns:
        assert turn.id.version == 7, f"expected uuid7, got version {turn.id.version}"


class FakeStreamingClientWithUsage:
    """Yields text tokens then a StreamUsage sentinel with exact counts."""

    def __init__(self, tokens: list[str], prompt_tokens: int, completion_tokens: int):
        self._tokens = tokens
        self._usage = StreamUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(answer="", prompt_tokens=0, completion_tokens=0)

    async def stream(self, request: ChatRequest) -> AsyncGenerator[str | StreamUsage]:
        for t in self._tokens:
            yield t
        yield self._usage


@pytest.mark.asyncio
async def test_frozen_clock_turns_ordered_by_id():
    """Frozen clock -> equal created_at; assistant id must sort after user id."""
    store = FakeChatHistoryStore()
    uc = ChatStreamUseCase(
        work_unit_factory=FakeChatWorkUnitFactory(FakeChunkRetriever(), store),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClient(["Hi", "!"]),
        token_budget=FakeChatTokenBudget(),
        id_generator=_ID_GEN,
        clock=FixedClock(),
    )
    from app.application.chat.use_cases.chat_stream import ChatQueryCommand

    async for _ in uc(ChatQueryCommand(user_id=UserId(uuid.uuid4()), message="hey")):
        pass

    user_turn, assistant_turn = store.saved[0], store.saved[1]
    assert user_turn.created_at == assistant_turn.created_at
    assert assistant_turn.id > user_turn.id


@pytest.mark.asyncio
async def test_exact_usage_recorded_when_sentinel_arrives():
    """Normal path: exact StreamUsage tokens are recorded, no estimate."""
    budget = FakeChatTokenBudget()
    uc = ChatStreamUseCase(
        work_unit_factory=FakeChatWorkUnitFactory(FakeChunkRetriever(), FakeChatHistoryStore()),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClientWithUsage(["Hello"], prompt_tokens=40, completion_tokens=2),
        token_budget=budget,
        id_generator=_ID_GEN,
        clock=FixedClock(),
    )
    from app.application.chat.use_cases.chat_stream import ChatQueryCommand

    async for _ in uc(ChatQueryCommand(user_id=UserId(uuid.uuid4()), message="hi")):
        pass

    assert budget.recorded == [42]


@pytest.mark.asyncio
@pytest.mark.skipif(
    bool(os.environ.get("MUTANT_UNDER_TEST")),
    reason="mutmut async-generator wrapper drops GeneratorExit propagation",
)
async def test_disconnect_records_token_estimate():
    """Client disconnects mid-stream with no usage sentinel -> record estimate.

    The user must not get those tokens for free: budget.record fires with a
    positive char-count estimate even though no StreamUsage ever arrived.
    """
    budget = FakeChatTokenBudget()
    uc = ChatStreamUseCase(
        work_unit_factory=FakeChatWorkUnitFactory(FakeChunkRetriever(), FakeChatHistoryStore()),
        embedder=FakeTextEmbedder(),
        ai_client=FakeStreamingClient(["aaaa", "bbbb", "cccc"]),
        token_budget=budget,
        id_generator=_ID_GEN,
        clock=FixedClock(),
    )
    from app.application.chat.use_cases.chat_stream import ChatQueryCommand

    gen = uc(ChatQueryCommand(user_id=UserId(uuid.uuid4()), message="question here"))
    await gen.__anext__()  # "aaaa"
    await gen.__anext__()  # "bbbb"
    await gen.aclose()  # disconnect before usage sentinel

    assert len(budget.recorded) == 1
    assert budget.recorded[0] > 0


def test_estimate_tokens_is_pure_and_positive():
    """estimate_tokens counts message + chunks + history + answer / 4, min 1."""
    from app.application.common.ports.chunk_retriever import RetrievedChunk

    chunk = RetrievedChunk(
        content="x" * 8, chunk_type="monthly_summary", period_label="Apr", metadata={}
    )
    history_turn = ChatTurn(
        id=uuid.uuid4(),
        user_id=UserId(uuid.uuid4()),
        role="user",
        content="y" * 4,
        chunks_used=(),
        created_at=datetime(2026, 6, 12, tzinfo=UTC),
    )
    request = ChatRequest(message="z" * 4, chunks=[chunk], history=[history_turn])
    # prompt chars = 4 + 8 + 4 = 16, answer = 4 -> (16 + 4) // 4 + 1 = 6
    assert estimate_tokens(request, "wwww") == 6
    # always at least 1 even for empty inputs
    assert estimate_tokens(ChatRequest(message="", chunks=[], history=[]), "") == 1
