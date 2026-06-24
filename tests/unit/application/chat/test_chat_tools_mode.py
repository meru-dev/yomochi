"""Tools-mode (function-calling) chat use-case tests (Task 4b).

These assert the parallel `tools` path: it never touches the embedder /
ChunkRetriever, dispatches tool calls to the right ChatTools method bound to the
request user_id, respects the iteration cap, streams the final answer, and
charges the token budget across every round.
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from app.application.chat.ports.chat_ai_client import (
    ChatResponse,
    ChatToolsRequest,
    StreamUsage,
)
from app.application.chat.ports.chat_history_store import ChatTurn
from app.application.chat.ports.work_unit import ChatWorkUnit
from app.application.chat.use_cases.chat_query import (
    ChatQueryCommand,
    ChatQueryUseCase,
)
from app.application.chat.use_cases.chat_stream import (
    ChatStreamDone,
    ChatStreamUseCase,
)
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.system.uuid7_id_generator import Uuid7ChatTurnIdGenerator

_ID_GEN = Uuid7ChatTurnIdGenerator()
_UID = UserId(uuid.uuid4())


class FixedClock:
    def __init__(self) -> None:
        self._instant = datetime(2026, 6, 12, tzinfo=UTC)

    def now(self) -> datetime:
        return self._instant

    def today(self):
        return self._instant.date()


class RecordingStore:
    def __init__(self) -> None:
        self.saved: list[ChatTurn] = []
        self.history: list[ChatTurn] = []
        self.last_n_calls = 0

    async def last_n(self, user_id, n):
        self.last_n_calls += 1
        return list(self.history)

    async def append_turn_pair(self, user_id, user_turn, assistant_turn):
        self.saved.extend([user_turn, assistant_turn])
        return user_turn, assistant_turn


class FakeWorkUnitFactory:
    def __init__(self, store) -> None:
        self._uow = ChatWorkUnit(history_store=store)

    def __call__(self):
        @asynccontextmanager
        async def _scope():
            yield self._uow

        return _scope()


class FakeBudget:
    def __init__(self) -> None:
        self.recorded: list[int] = []
        self.checks = 0

    async def check(self, user_id) -> None:
        self.checks += 1

    async def record(self, user_id, tokens: int) -> None:
        self.recorded.append(tokens)


class RecordingChatTools:
    """Records (method, user_id, kwargs) and returns trivial typed-ish results."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def get_month_summary(self, user_id, year, month):
        self.calls.append(("get_month_summary", user_id, {"year": year, "month": month}))
        from app.application.chat.ports.chat_tools import MonthSummaryResult

        return MonthSummaryResult(year=year, month=month, by_currency=[])

    async def get_category_trend(self, user_id, category, n_months):
        self.calls.append(
            ("get_category_trend", user_id, {"category": category, "n_months": n_months})
        )
        from app.application.chat.ports.chat_tools import CategoryTrendResult

        return CategoryTrendResult(category=category, series=[])

    async def get_spend_window(self, user_id, start_date, end_date):
        self.calls.append(
            ("get_spend_window", user_id, {"start_date": start_date, "end_date": end_date})
        )
        from app.application.chat.ports.chat_tools import SpendWindowResult

        return SpendWindowResult(start_date=start_date, end_date=end_date, by_currency=[])

    async def get_user_profile(self, user_id):
        self.calls.append(("get_user_profile", user_id, {}))
        from app.application.chat.ports.chat_tools import UserProfileResult

        return UserProfileResult(months_covered=4, by_currency=[])

    async def search_transactions(self, user_id, text, limit):
        self.calls.append(("search_transactions", user_id, {"text": text, "limit": limit}))
        from app.application.chat.ports.chat_tools import SearchTransactionsResult

        return SearchTransactionsResult(query=text, matches=[])

    async def list_categories(self, user_id):
        self.calls.append(("list_categories", user_id, {}))
        from app.application.chat.ports.chat_tools import ListCategoriesResult

        return ListCategoriesResult(categories=[])


class FakeToolCallingClient:
    """Fake ChatAIClient driving the executor.

    On chat_with_tools it invokes the executor once for each scripted call, then
    returns the final answer. `tools_used` reflects the executed names. Asserts
    chat()/stream() (the RAG entry points) are never called.
    """

    def __init__(self, scripted_calls, answer="42 JPY on cafes."):
        self._scripted = scripted_calls  # list[(name, args)]
        self._answer = answer
        self.captured_request: ChatToolsRequest | None = None

    async def chat(self, request):
        raise AssertionError("tools mode must use chat_with_tools, not chat")

    async def stream(self, request):
        raise AssertionError("tools mode must use stream_with_tools, not stream")
        yield  # pragma: no cover

    async def chat_with_tools(self, request: ChatToolsRequest) -> ChatResponse:
        self.captured_request = request
        used = []
        for name, args in self._scripted:
            await request.tool_executor(name, args)
            used.append(name)
        return ChatResponse(
            answer=self._answer,
            prompt_tokens=120,
            completion_tokens=30,
            tools_used=tuple(used),
        )

    async def stream_with_tools(
        self, request: ChatToolsRequest
    ) -> AsyncGenerator[str | StreamUsage]:
        self.captured_request = request
        used = []
        for name, args in self._scripted:
            await request.tool_executor(name, args)
            used.append(name)
        for tok in self._answer.split(" "):
            yield tok + " "
        # usage covers ALL rounds (tool selection + final answer); the sentinel
        # also carries tools_used so the streamed turn records tool provenance.
        yield StreamUsage(prompt_tokens=200, completion_tokens=50, tools_used=tuple(used))


def _make_query_uc(client, tools, store=None, budget=None):
    return ChatQueryUseCase(
        work_unit_factory=FakeWorkUnitFactory(store or RecordingStore()),
        ai_client=client,
        token_budget=budget or FakeBudget(),
        id_generator=_ID_GEN,
        clock=FixedClock(),
        chat_tools=tools,
    )


@pytest.mark.asyncio
async def test_tools_mode_dispatches_to_right_method_with_user_id_and_args():
    tools = RecordingChatTools()
    client = FakeToolCallingClient([("get_month_summary", {"year": 2026, "month": 5})])
    uc = _make_query_uc(client, tools)

    result = await uc(ChatQueryCommand(user_id=_UID, message="How much in May?"))

    assert result.answer == "42 JPY on cafes."
    assert len(tools.calls) == 1
    name, uid, kwargs = tools.calls[0]
    assert name == "get_month_summary"
    assert uid == str(_UID)  # bound server-side, not from the model
    assert kwargs == {"year": 2026, "month": 5}


@pytest.mark.asyncio
async def test_tools_mode_does_not_touch_embedder_or_retriever():
    tools = RecordingChatTools()
    client = FakeToolCallingClient([("get_user_profile", {})])
    uc = _make_query_uc(client, tools)
    # The chat work unit no longer carries any chunk retriever — tools-only path.
    result = await uc(ChatQueryCommand(user_id=_UID, message="how am I doing?"))
    assert result.answer
    assert tools.calls[0][0] == "get_user_profile"


@pytest.mark.asyncio
async def test_tools_mode_records_budget_across_rounds():
    budget = FakeBudget()
    tools = RecordingChatTools()
    client = FakeToolCallingClient([("get_user_profile", {})])
    uc = _make_query_uc(client, tools, budget=budget)
    await uc(ChatQueryCommand(user_id=_UID, message="hi"))
    # 120 prompt + 30 completion = 150 across all rounds.
    assert budget.recorded == [150]


@pytest.mark.asyncio
async def test_tools_mode_saves_turns_with_tool_metadata():
    store = RecordingStore()
    tools = RecordingChatTools()
    client = FakeToolCallingClient(
        [("get_month_summary", {"year": 2026, "month": 5}), ("get_user_profile", {})]
    )
    uc = _make_query_uc(client, tools, store=store)
    await uc(ChatQueryCommand(user_id=_UID, message="q"))
    assert len(store.saved) == 2
    assistant = store.saved[1]
    assert assistant.role == "assistant"
    assert assistant.chunks_used == ({"tool": "get_month_summary"}, {"tool": "get_user_profile"})


@pytest.mark.asyncio
async def test_executor_binds_user_id_for_every_tool():
    """Each of the 5 tools dispatches with the bound user_id and parsed args."""
    tools = RecordingChatTools()
    client = FakeToolCallingClient(
        [
            ("get_month_summary", {"year": 2026, "month": 1}),
            ("get_category_trend", {"category": "Food", "n_months": 3}),
            ("get_spend_window", {"start_date": "2026-01-01", "end_date": "2026-01-31"}),
            ("get_user_profile", {}),
            ("search_transactions", {"text": "starbucks", "limit": 5}),
        ]
    )
    uc = _make_query_uc(client, tools)
    await uc(ChatQueryCommand(user_id=_UID, message="everything"))

    names = [c[0] for c in tools.calls]
    assert names == [
        "get_month_summary",
        "get_category_trend",
        "get_spend_window",
        "get_user_profile",
        "search_transactions",
    ]
    assert all(c[1] == str(_UID) for c in tools.calls)
    # date strings parsed to date objects
    from datetime import date

    window = next(c for c in tools.calls if c[0] == "get_spend_window")
    assert window[2]["start_date"] == date(2026, 1, 1)
    assert window[2]["end_date"] == date(2026, 1, 31)


@pytest.mark.asyncio
async def test_executor_unknown_tool_returns_error_payload():
    from app.application.chat._tools_executor import build_tool_executor

    tools = RecordingChatTools()
    executor = build_tool_executor(tools, _UID)
    out = await executor("does_not_exist", {})
    assert "error" in out
    assert tools.calls == []


@pytest.mark.asyncio
async def test_executor_bad_args_returns_error_payload():
    from app.application.chat._tools_executor import build_tool_executor

    tools = RecordingChatTools()
    executor = build_tool_executor(tools, _UID)
    out = await executor("get_month_summary", {"year": "notanint"})
    assert "error" in out


@pytest.mark.asyncio
async def test_executor_dispatches_list_categories_with_no_args():
    """list_categories dispatches with no model-supplied args; user_id is bound server-side."""
    from app.application.chat._tools_executor import build_tool_executor

    tools = RecordingChatTools()
    executor = build_tool_executor(tools, _UID)
    out = await executor("list_categories", {})
    # Must be json-serialisable and have the expected shape
    import json

    serialised = json.dumps(out)  # must not raise
    assert "categories" in out
    assert isinstance(out["categories"], list)
    # user_id was bound server-side
    assert len(tools.calls) == 1
    assert tools.calls[0][0] == "list_categories"
    assert tools.calls[0][1] == str(_UID)
    assert '"categories"' in serialised


# ── streaming ───────────────────────────────────────────────────────────────


def _make_stream_uc(client, tools, store=None, budget=None):
    return ChatStreamUseCase(
        work_unit_factory=FakeWorkUnitFactory(store or RecordingStore()),
        ai_client=client,
        token_budget=budget or FakeBudget(),
        id_generator=_ID_GEN,
        clock=FixedClock(),
        chat_tools=tools,
    )


@pytest.mark.asyncio
async def test_stream_tools_mode_streams_final_answer_and_emits_usage():
    budget = FakeBudget()
    store = RecordingStore()
    tools = RecordingChatTools()
    client = FakeToolCallingClient([("get_user_profile", {})], answer="You spent forty two")
    uc = _make_stream_uc(client, tools, store=store, budget=budget)

    items = [i async for i in uc(ChatQueryCommand(user_id=_UID, message="q"))]
    text = "".join(i for i in items if isinstance(i, str))
    dones = [i for i in items if isinstance(i, ChatStreamDone)]

    assert "You spent forty two" in text
    assert len(dones) == 1
    # tool round executed
    assert tools.calls[0][0] == "get_user_profile"
    # usage across ALL rounds: 200 + 50 = 250
    assert budget.recorded == [250]
    # turns saved
    assert len(store.saved) == 2
    assert store.saved[1].content.strip() == "You spent forty two"
    # streamed turn records the same tool provenance as the non-streamed path
    assert store.saved[1].chunks_used == ({"tool": "get_user_profile"},)


@pytest.mark.asyncio
async def test_stream_tools_mode_persists_tool_metadata_from_sentinel():
    """IMPORTANT 1: streamed tools turn must record tools_used (not chunks_used=())."""
    store = RecordingStore()
    tools = RecordingChatTools()
    client = FakeToolCallingClient(
        [("get_month_summary", {"year": 2026, "month": 5}), ("get_user_profile", {})],
        answer="done",
    )
    uc = _make_stream_uc(client, tools, store=store)
    [i async for i in uc(ChatQueryCommand(user_id=_UID, message="q"))]
    assistant = store.saved[1]
    assert assistant.chunks_used == ({"tool": "get_month_summary"}, {"tool": "get_user_profile"})


@pytest.mark.asyncio
async def test_stream_tools_mode_does_not_touch_embedder():
    tools = RecordingChatTools()
    client = FakeToolCallingClient([("get_user_profile", {})], answer="ok")
    uc = _make_stream_uc(client, tools)
    items = [i async for i in uc(ChatQueryCommand(user_id=_UID, message="q"))]
    assert any(isinstance(i, ChatStreamDone) for i in items)


class FloorThenAnswerClient:
    """Emits an early floor StreamUsage (tool-round tokens) BEFORE streaming.

    Mirrors the adapter's cap-hit path: tool rounds are paid for, a floor
    sentinel is yielded, then the final answer streams and a total sentinel
    follows. Lets us prove a disconnect after the floor still bills the tools.
    """

    def __init__(self, floor_tokens=(90, 9), final_tokens=(130, 17), answer="forced final"):
        self._floor = floor_tokens
        self._final = final_tokens
        self._answer = answer

    async def chat(self, request):  # pragma: no cover - tools path only
        raise AssertionError("tools mode must not call chat")

    async def stream(self, request):  # pragma: no cover - tools path only
        raise AssertionError("tools mode must not call stream")
        yield

    async def chat_with_tools(self, request):  # pragma: no cover - streaming path only
        raise AssertionError("streaming tools mode must use stream_with_tools")

    async def stream_with_tools(self, request) -> AsyncGenerator[str | StreamUsage]:
        # Early floor sentinel — emitted BEFORE any token.
        yield StreamUsage(
            prompt_tokens=self._floor[0],
            completion_tokens=self._floor[1],
            tools_used=("get_user_profile",),
        )
        for tok in self._answer.split(" "):
            yield tok + " "
        yield StreamUsage(
            prompt_tokens=self._final[0],
            completion_tokens=self._final[1],
            tools_used=("get_user_profile",),
        )


@pytest.mark.asyncio
async def test_stream_tools_mode_disconnect_after_tool_rounds_bills_floor():
    """IMPORTANT 2: disconnect after the floor sentinel but before the final
    answer still charges the paid tool-round tokens (not zero)."""
    budget = FakeBudget()
    tools = RecordingChatTools()
    client = FloorThenAnswerClient(floor_tokens=(90, 9))
    uc = _make_stream_uc(client, tools, budget=budget)

    gen = uc(ChatQueryCommand(user_id=_UID, message="q"))
    await gen.__anext__()  # consume the first streamed token (floor already seen)
    await gen.aclose()  # disconnect before the final total sentinel

    # The early floor (90 + 9 = 99) is billed, not a char estimate, not zero.
    assert budget.recorded == [99]


@pytest.mark.asyncio
async def test_stream_tools_mode_normal_path_bills_final_total_once():
    """No double-count: the floor + final sentinels resolve to ONE record of the
    final total when the stream completes normally."""
    budget = FakeBudget()
    tools = RecordingChatTools()
    client = FloorThenAnswerClient(floor_tokens=(90, 9), final_tokens=(130, 17))
    uc = _make_stream_uc(client, tools, budget=budget)

    [i async for i in uc(ChatQueryCommand(user_id=_UID, message="q"))]

    # final total wins: 130 + 17 = 147, recorded exactly once.
    assert budget.recorded == [147]
