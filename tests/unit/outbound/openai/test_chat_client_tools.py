"""OpenAI chat-client function-calling loop tests (Task 4b).

Drive OpenAIChatClient.chat_with_tools / stream_with_tools with a fake OpenAI
SDK client to assert: the loop executes tool_calls, accumulates usage across all
rounds, stops at the iteration cap, and the streaming variant resolves tool
rounds non-streamed then streams only the final answer.

Also covers: two tool calls in one round execute concurrently and their
results are appended in the original request order.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion_message_function_tool_call import Function

from app.application.chat.ports.chat_ai_client import ChatToolsRequest, StreamUsage
from app.outbound.adapters.openai._gateway import ContentDelta, ToolCallsDelta, UsageInfo
from app.outbound.adapters.openai.chat_client import OpenAIChatClient


def _assembled_call(call_id, name, arguments):
    """Assembled tool-call dict shape carried by ToolCallsDelta."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _choice(content=None, tool_calls=None):
    return SimpleNamespace(message=_msg(content, tool_calls))


def _usage(p, c):
    return SimpleNamespace(prompt_tokens=p, completion_tokens=c)


def _tool_call(call_id, name, args):
    # Real SDK type so the adapter's isinstance(function-tool-call) filter passes.
    return ChatCompletionMessageFunctionToolCall(
        id=call_id,
        type="function",
        function=Function(name=name, arguments=json.dumps(args)),
    )


class FakeCompletions:
    """Returns scripted responses in sequence on each .create() call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeOpenAIClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class FakeGateway:
    """Scripted fake gateway.

    - ``call`` runs the fn against a scripted fake OpenAI client (non-streamed
      tools path: chat_with_tools).
    - ``stream_call_with_tools`` yields the next scripted per-round event list
      (each list is one round of ContentDelta / ToolCallsDelta / UsageInfo).
      A snapshot of the messages seen each round is captured for assertions.
    - ``stream_call`` yields ``stream_items`` (the forced-final / RAG path).
    """

    def __init__(self, call_client=None, stream_items=None, tool_stream_rounds=None):
        self._call_client = call_client
        self._stream_items = stream_items or []
        self._tool_stream_rounds = list(tool_stream_rounds or [])
        self.stream_messages = None
        # Messages passed to stream_call_with_tools, captured per round.
        self.tool_round_messages: list[list[dict]] = []
        self.tool_round_tools: list[list[dict]] = []

    async def call(self, *, endpoint, fn, timeout=None):
        return await fn(self._call_client)

    async def stream_call(
        self,
        *,
        endpoint,
        messages,
        model,
        temperature,
        max_tokens,
        timeout=None,
        prompt_cache_key=None,
    ):
        self.stream_messages = messages
        for item in self._stream_items:
            yield item

    async def stream_call_with_tools(
        self,
        *,
        endpoint,
        messages,
        model,
        temperature,
        max_tokens,
        tools,
        timeout=None,
        prompt_cache_key=None,
    ):
        # Snapshot the messages/tools for this round before the caller mutates them.
        self.tool_round_messages.append(list(messages))
        self.tool_round_tools.append(tools)
        events = self._tool_stream_rounds.pop(0)
        for ev in events:
            yield ev


async def _noop_executor(name, args):
    return {"ok": name, "args": args}


@pytest.mark.asyncio
async def test_chat_with_tools_executes_then_answers_and_sums_usage():
    # Round 1: model asks for a tool. Round 2 (no tools offered): final answer.
    responses = [
        SimpleNamespace(
            choices=[_choice(tool_calls=[_tool_call("c1", "get_user_profile", {})])],
            usage=_usage(100, 10),
        ),
        SimpleNamespace(
            choices=[_choice(content="You are doing fine.")],
            usage=_usage(80, 20),
        ),
    ]
    executed = []

    async def executor(name, args):
        executed.append((name, args))
        return {"months_covered": 4}

    gateway = FakeGateway(call_client=FakeOpenAIClient(responses))
    client = OpenAIChatClient(gateway=gateway, model="gpt-4o-mini", read_timeout_seconds=30.0)

    resp = await client.chat_with_tools(
        ChatToolsRequest(message="how am I?", history=[], tool_executor=executor)
    )

    assert resp.answer == "You are doing fine."
    assert executed == [("get_user_profile", {})]
    assert resp.tools_used == ("get_user_profile",)
    # usage summed across the tool round (100/10) + final round (80/20)
    assert resp.prompt_tokens == 180
    assert resp.completion_tokens == 30


@pytest.mark.asyncio
async def test_chat_with_tools_no_tool_calls_answers_directly():
    responses = [
        SimpleNamespace(choices=[_choice(content="Direct answer.")], usage=_usage(50, 5)),
        SimpleNamespace(choices=[_choice(content="Direct answer.")], usage=_usage(50, 5)),
    ]
    gateway = FakeGateway(call_client=FakeOpenAIClient(responses))
    client = OpenAIChatClient(gateway=gateway, model="gpt-4o-mini", read_timeout_seconds=30.0)
    resp = await client.chat_with_tools(
        ChatToolsRequest(message="hi", history=[], tool_executor=_noop_executor)
    )
    assert resp.answer == "Direct answer."
    assert resp.tools_used == ()


@pytest.mark.asyncio
async def test_iteration_cap_stops_the_loop():
    # Model keeps requesting tools forever; cap=2 means 2 tool rounds + 1 final.
    def tool_round(n):
        return SimpleNamespace(
            choices=[_choice(tool_calls=[_tool_call(f"c{n}", "get_user_profile", {})])],
            usage=_usage(10, 1),
        )

    # cap=2 → 2 tool rounds consumed, then one forced final answer.
    final = SimpleNamespace(choices=[_choice(content="forced answer")], usage=_usage(5, 1))
    responses = [tool_round(1), tool_round(2), final]

    executed = []

    async def executor(name, args):
        executed.append(name)
        return {}

    gateway = FakeGateway(call_client=FakeOpenAIClient(responses))
    client = OpenAIChatClient(
        gateway=gateway, model="gpt-4o-mini", read_timeout_seconds=30.0, max_tool_iterations=2
    )
    resp = await client.chat_with_tools(
        ChatToolsRequest(message="loop", history=[], tool_executor=executor)
    )
    # exactly 2 tool rounds executed (cap), then final answer
    assert len(executed) == 2
    assert resp.answer == "forced answer"


# ---------------------------------------------------------------------------
# Streaming WITH tools every round (the 6 brief scenarios)
# ---------------------------------------------------------------------------


def _stream_client(tool_stream_rounds, *, stream_items=None):
    gateway = FakeGateway(tool_stream_rounds=tool_stream_rounds, stream_items=stream_items)
    client = OpenAIChatClient(gateway=gateway, model="gpt-4o-mini", read_timeout_seconds=30.0)
    return gateway, client


async def _collect_stream(client, executor=_noop_executor, message="q"):
    out = []
    async for item in client.stream_with_tools(
        ChatToolsRequest(message=message, history=[], tool_executor=executor)
    ):
        out.append(item)
    return out


@pytest.mark.asyncio
async def test_stream_single_round_no_tools_streams_tokens():
    # Scenario 1: model streams the answer directly in one round, no tools.
    rounds = [
        [
            ContentDelta("Hel"),
            ContentDelta("lo"),
            ContentDelta(" there"),
            UsageInfo(prompt_tokens=50, completion_tokens=6),
        ]
    ]
    _gateway, client = _stream_client(rounds)
    out = await _collect_stream(client)

    tokens = [i for i in out if isinstance(i, str)]
    usages = [i for i in out if isinstance(i, StreamUsage)]
    # multiple content yields — NOT one block
    assert tokens == ["Hel", "lo", " there"]
    assert len(usages) == 1
    assert (usages[0].prompt_tokens, usages[0].completion_tokens) == (50, 6)
    assert usages[0].tools_used == ()


@pytest.mark.asyncio
async def test_stream_one_tool_round_then_streamed_answer():
    # Scenario 2: round 1 streams a tool_calls delta (assembled from arg
    # fragments) → tool executed → round 2 streams answer tokens.
    rounds = [
        [
            ToolCallsDelta([_assembled_call("c1", "get_user_profile", "{}")]),
            UsageInfo(prompt_tokens=90, completion_tokens=9),
        ],
        [
            ContentDelta("All"),
            ContentDelta(" good"),
            UsageInfo(prompt_tokens=40, completion_tokens=8),
        ],
    ]
    executed = []

    async def executor(name, args):
        executed.append((name, args))
        return {"months_covered": 4}

    gateway, client = _stream_client(rounds)
    out = await _collect_stream(client, executor=executor)

    tokens = [i for i in out if isinstance(i, str)]
    usages = [i for i in out if isinstance(i, StreamUsage)]
    assert executed == [("get_user_profile", {})]
    # answer arrives as multiple tokens
    assert tokens == ["All", " good"]
    # a floor StreamUsage after the tool round + the final total
    assert len(usages) == 2
    floor, final = usages
    assert (floor.prompt_tokens, floor.completion_tokens) == (90, 9)
    assert floor.tools_used == ("get_user_profile",)
    # floor emitted before any answer token
    assert out.index(floor) < out.index("All")
    # final = round1 90/9 + round2 40/8
    assert (final.prompt_tokens, final.completion_tokens) == (130, 17)
    assert final.tools_used == ("get_user_profile",)
    # round 2's messages include the tool-role result, in order after assistant turn
    round2_messages = gateway.tool_round_messages[1]
    tool_msgs = [m for m in round2_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "c1"


@pytest.mark.asyncio
async def test_stream_multiple_tool_calls_one_round_concurrent_in_order():
    # Scenario 3: two tool calls assembled in one streamed round, executed
    # concurrently, tool messages appended in request order.
    rounds = [
        [
            ToolCallsDelta(
                [
                    _assembled_call("c1", "get_user_profile", "{}"),
                    _assembled_call("c2", "get_month_summary", '{"year": 2026, "month": 5}'),
                ]
            ),
            UsageInfo(prompt_tokens=100, completion_tokens=10),
        ],
        [ContentDelta("done"), UsageInfo(prompt_tokens=20, completion_tokens=3)],
    ]
    execution_order = []

    async def recording_executor(name, args):
        await asyncio.sleep(0)
        execution_order.append(name)
        return {"tool": name, "args": args}

    gateway, client = _stream_client(rounds)
    out = await _collect_stream(client, executor=recording_executor)

    assert set(execution_order) == {"get_user_profile", "get_month_summary"}
    # tool messages appended in request order (c1 then c2)
    round2_messages = gateway.tool_round_messages[1]
    tool_msgs = [m for m in round2_messages if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2"]
    # final sentinel carries both tools in order
    usages = [i for i in out if isinstance(i, StreamUsage)]
    assert usages[-1].tools_used == ("get_user_profile", "get_month_summary")


@pytest.mark.asyncio
async def test_stream_argument_fragment_assembly():
    # Scenario 4: arguments arrive in several ToolCallsDelta-equivalent fragments;
    # here we model the ASSEMBLED result (assembly is unit-tested at gateway level
    # in test_gateway_stream_call_with_tools) and assert it is parsed to valid args.
    rounds = [
        [
            ToolCallsDelta(
                [_assembled_call("c1", "get_month_summary", '{"year": 2026, "month": 5}')]
            ),
            UsageInfo(prompt_tokens=30, completion_tokens=4),
        ],
        [ContentDelta("ok"), UsageInfo(prompt_tokens=10, completion_tokens=1)],
    ]
    seen_args = []

    async def executor(name, args):
        seen_args.append(args)
        return {}

    _gateway, client = _stream_client(rounds)
    await _collect_stream(client, executor=executor)
    # concatenated arguments parsed into a valid dict before execution
    assert seen_args == [{"year": 2026, "month": 5}]


@pytest.mark.asyncio
async def test_stream_cap_hit_forces_final_answer_no_tools():
    # Scenario 5: model keeps requesting tools past the cap → forced final
    # streamed answer with no tools (via stream_call); billing includes all rounds.
    rounds = [
        [
            ToolCallsDelta([_assembled_call("c1", "get_user_profile", "{}")]),
            UsageInfo(prompt_tokens=10, completion_tokens=1),
        ],
        [
            ToolCallsDelta([_assembled_call("c2", "get_user_profile", "{}")]),
            UsageInfo(prompt_tokens=10, completion_tokens=1),
        ],
    ]
    stream_items = ["forced", " answer", UsageInfo(prompt_tokens=5, completion_tokens=2)]
    gateway = FakeGateway(tool_stream_rounds=rounds, stream_items=stream_items)
    client = OpenAIChatClient(
        gateway=gateway, model="gpt-4o-mini", read_timeout_seconds=30.0, max_tool_iterations=2
    )
    out = await _collect_stream(client)

    tokens = [i for i in out if isinstance(i, str)]
    usages = [i for i in out if isinstance(i, StreamUsage)]
    assert "".join(tokens) == "forced answer"
    # forced final round used stream_call (no tools)
    assert gateway.stream_messages is not None
    # final total = 2 tool rounds (10/1 each) + forced (5/2) = 25/4
    assert (usages[-1].prompt_tokens, usages[-1].completion_tokens) == (25, 4)
    assert usages[-1].tools_used == ("get_user_profile", "get_user_profile")


@pytest.mark.asyncio
async def test_stream_usage_accounting_sums_across_rounds():
    # Scenario 6: per-round usage sums correctly; final sentinel == sum of rounds.
    rounds = [
        [
            ToolCallsDelta([_assembled_call("c1", "get_user_profile", "{}")]),
            UsageInfo(prompt_tokens=11, completion_tokens=2),
        ],
        [
            ToolCallsDelta([_assembled_call("c2", "list_categories", "{}")]),
            UsageInfo(prompt_tokens=22, completion_tokens=3),
        ],
        [
            ContentDelta("answer"),
            UsageInfo(prompt_tokens=33, completion_tokens=4),
        ],
    ]
    client = OpenAIChatClient(
        gateway=FakeGateway(tool_stream_rounds=rounds),
        model="gpt-4o-mini",
        read_timeout_seconds=30.0,
        max_tool_iterations=5,
    )
    out = await _collect_stream(client)
    usages = [i for i in out if isinstance(i, StreamUsage)]
    final = usages[-1]
    assert final.prompt_tokens == 11 + 22 + 33
    assert final.completion_tokens == 2 + 3 + 4
    assert final.tools_used == ("get_user_profile", "list_categories")


# ---------------------------------------------------------------------------
# Concurrent tool execution within a single round
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_tool_calls_in_one_round_both_execute_in_request_order():
    """Two tool calls in one round must both execute and results appended in
    the same order as the function_calls list (OpenAI requirement for stable
    tool_call_id ↔ tool message pairing).
    """
    execution_order: list[str] = []

    async def recording_executor(name, args):
        # Small sleep ensures concurrency reveals ordering issues if order isn't
        # preserved explicitly.
        await asyncio.sleep(0)
        execution_order.append(name)
        return {"tool": name, "args": args}

    responses = [
        # Round 1: two tool calls in a single response.
        SimpleNamespace(
            choices=[
                _choice(
                    tool_calls=[
                        _tool_call("c1", "get_user_profile", {}),
                        _tool_call("c2", "get_month_summary", {"year": 2026, "month": 5}),
                    ]
                )
            ],
            usage=_usage(100, 10),
        ),
        # Round 2: final answer after seeing both tool results.
        SimpleNamespace(
            choices=[_choice(content="You spent a lot in May.")],
            usage=_usage(80, 20),
        ),
    ]

    gateway = FakeGateway(call_client=FakeOpenAIClient(responses))
    client = OpenAIChatClient(gateway=gateway, model="gpt-4o-mini", read_timeout_seconds=30.0)

    resp = await client.chat_with_tools(
        ChatToolsRequest(message="how was May?", history=[], tool_executor=recording_executor)
    )

    # Both tools were executed.
    assert set(execution_order) == {"get_user_profile", "get_month_summary"}

    # tools_used must reflect request order (c1 → get_user_profile, c2 → get_month_summary).
    assert resp.tools_used == ("get_user_profile", "get_month_summary")

    # The messages list appended to OpenAI must contain two tool-role messages
    # in the same order as the original function_calls list.
    second_call_messages = gateway._call_client.chat.completions.calls[1]["messages"]
    tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["tool_call_id"] == "c1"
    assert tool_msgs[1]["tool_call_id"] == "c2"

    # Sanity: final answer surfaced correctly.
    assert resp.answer == "You spent a lot in May."


@pytest.mark.asyncio
async def test_today_date_prepended_to_system_prompt():
    from datetime import date

    responses = [
        SimpleNamespace(choices=[_choice(content="Answer.")], usage=_usage(50, 5)),
    ]
    gateway = FakeGateway(call_client=FakeOpenAIClient(responses))
    client = OpenAIChatClient(gateway=gateway, model="gpt-4o-mini", read_timeout_seconds=30.0)

    today = date(2026, 6, 22)
    await client.chat_with_tools(
        ChatToolsRequest(message="how am I?", history=[], tool_executor=_noop_executor, today=today)
    )

    first_call_messages = gateway._call_client.chat.completions.calls[0]["messages"]
    system_content = next(m["content"] for m in first_call_messages if m["role"] == "system")
    assert system_content.startswith("Today's date is 2026-06-22.")


def _usage_cached(p, c, cached):
    return SimpleNamespace(
        prompt_tokens=p,
        completion_tokens=c,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
    )


@pytest.mark.asyncio
async def test_non_stream_records_cached_tokens():
    """Cached prompt tokens on the non-stream chat path hit the cache counter."""
    from app.outbound.observability.prometheus import openai_cached_tokens_total

    model = "gpt-4o-mini"
    responses = [
        SimpleNamespace(choices=[_choice(content="Answer.")], usage=_usage_cached(1200, 20, 1024)),
    ]
    gateway = FakeGateway(call_client=FakeOpenAIClient(responses))
    client = OpenAIChatClient(gateway=gateway, model=model, read_timeout_seconds=30.0)

    counter = openai_cached_tokens_total.labels(endpoint="chat_query", model=model)
    before = counter._value.get()
    await client.chat_with_tools(
        ChatToolsRequest(message="hi", history=[], tool_executor=_noop_executor)
    )
    assert counter._value.get() - before == 1024


@pytest.mark.asyncio
async def test_prompt_cache_key_forwarded_non_stream():
    """Prompt_cache_key is passed through to the non-stream create() call."""
    responses = [
        SimpleNamespace(choices=[_choice(content="Answer.")], usage=_usage(50, 5)),
    ]
    gateway = FakeGateway(call_client=FakeOpenAIClient(responses))
    client = OpenAIChatClient(gateway=gateway, model="gpt-4o-mini", read_timeout_seconds=30.0)

    await client.chat_with_tools(
        ChatToolsRequest(message="hi", history=[], tool_executor=_noop_executor, cache_key="user-9")
    )

    assert gateway._call_client.chat.completions.calls[0]["prompt_cache_key"] == "user-9"
