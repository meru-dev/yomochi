from unittest.mock import AsyncMock, MagicMock

import pytest

from app.outbound.adapters.openai._gateway.gateway import (
    ContentDelta,
    OpenAIGateway,
    ToolCallsDelta,
    UsageInfo,
)


def _fake_gateway(mock_client):
    breaker = AsyncMock()
    breaker.__aenter__ = AsyncMock(return_value=None)
    breaker.__aexit__ = AsyncMock(return_value=False)
    breaker.context = MagicMock()
    breaker.context.state = "closed"

    gateway = MagicMock()
    gateway._client.with_options.return_value = mock_client
    gateway._default_timeout = 30.0
    gateway._default_scoped_client = mock_client
    gateway._breakers = {"chat": breaker, "embeddings": breaker, "vision": breaker}
    gateway._limiter = AsyncMock()
    gateway._limiter.__aenter__ = AsyncMock(return_value=None)
    gateway._limiter.__aexit__ = AsyncMock(return_value=False)
    return gateway


@pytest.mark.asyncio
async def test_stream_call_yields_content_tokens():
    """stream_call should yield each text delta from streaming response."""

    def _chunk(content):
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = content
        c.usage = None
        return c

    final_chunk = MagicMock()
    final_chunk.choices = []
    final_chunk.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    chunks = [_chunk("Hello"), _chunk(" world"), final_chunk]

    async def _async_iter():
        for chunk in chunks:
            yield chunk

    fake_stream = _async_iter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_stream)

    breaker = AsyncMock()
    breaker.__aenter__ = AsyncMock(return_value=None)
    breaker.__aexit__ = AsyncMock(return_value=False)
    breaker.context = MagicMock()
    breaker.context.state = "closed"

    gateway = MagicMock()
    gateway._client.with_options.return_value = mock_client
    gateway._default_timeout = 30.0
    gateway._default_scoped_client = mock_client
    gateway._breakers = {"chat": breaker, "embeddings": breaker, "vision": breaker}
    gateway._limiter = AsyncMock()
    gateway._limiter.__aenter__ = AsyncMock(return_value=None)
    gateway._limiter.__aexit__ = AsyncMock(return_value=False)

    items = []
    async for item in OpenAIGateway.stream_call(
        gateway,
        endpoint="chat",
        messages=[{"role": "user", "content": "Hi"}],
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=800,
    ):
        items.append(item)

    tokens = [i for i in items if isinstance(i, str)]
    usages = [i for i in items if isinstance(i, UsageInfo)]
    assert tokens == ["Hello", " world"]
    assert usages == [UsageInfo(prompt_tokens=10, completion_tokens=5)]


def _tc_fragment(index, *, call_id=None, name=None, arguments=None):
    fn = None
    if name is not None or arguments is not None:
        fn = MagicMock()
        fn.name = name
        fn.arguments = arguments
    frag = MagicMock()
    frag.index = index
    frag.id = call_id
    frag.function = fn
    return frag


def _tool_chunk(*, content=None, tool_calls=None, finish_reason=None):
    c = MagicMock()
    choice = MagicMock()
    choice.delta.content = content
    choice.delta.tool_calls = tool_calls
    choice.finish_reason = finish_reason
    c.choices = [choice]
    c.usage = None
    return c


@pytest.mark.asyncio
async def test_stream_call_with_tools_assembles_argument_fragments():
    """Argument fragments arriving across chunks are concatenated per index, then
    emitted ONCE as a ToolCallsDelta on finish_reason='tool_calls'."""
    chunks = [
        _tool_chunk(
            tool_calls=[_tc_fragment(0, call_id="c1", name="get_month_summary", arguments="")]
        ),
        _tool_chunk(tool_calls=[_tc_fragment(0, arguments='{"year": 20')]),
        _tool_chunk(tool_calls=[_tc_fragment(0, arguments='26, "month": 5}')]),
        _tool_chunk(finish_reason="tool_calls"),
    ]
    final_chunk = MagicMock()
    final_chunk.choices = []
    final_chunk.usage = MagicMock(prompt_tokens=30, completion_tokens=4)
    chunks.append(final_chunk)

    async def _async_iter():
        for chunk in chunks:
            yield chunk

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_async_iter())
    gateway = _fake_gateway(mock_client)

    items = []
    async for item in OpenAIGateway.stream_call_with_tools(
        gateway,
        endpoint="chat",
        messages=[{"role": "user", "content": "Hi"}],
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=800,
        tools=[{"type": "function"}],
    ):
        items.append(item)

    tool_deltas = [i for i in items if isinstance(i, ToolCallsDelta)]
    usages = [i for i in items if isinstance(i, UsageInfo)]
    assert len(tool_deltas) == 1
    calls = tool_deltas[0].tool_calls
    assert calls == [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "get_month_summary", "arguments": '{"year": 2026, "month": 5}'},
        }
    ]
    assert usages == [UsageInfo(prompt_tokens=30, completion_tokens=4)]


@pytest.mark.asyncio
async def test_stream_call_with_tools_streams_content_then_usage():
    """When the model answers, content arrives as ContentDelta events + usage."""
    chunks = [
        _tool_chunk(content="Hel"),
        _tool_chunk(content="lo", finish_reason="stop"),
    ]
    final_chunk = MagicMock()
    final_chunk.choices = []
    final_chunk.usage = MagicMock(prompt_tokens=12, completion_tokens=2)
    chunks.append(final_chunk)

    async def _async_iter():
        for chunk in chunks:
            yield chunk

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_async_iter())
    gateway = _fake_gateway(mock_client)

    items = []
    async for item in OpenAIGateway.stream_call_with_tools(
        gateway,
        endpoint="chat",
        messages=[{"role": "user", "content": "Hi"}],
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=800,
        tools=[{"type": "function"}],
    ):
        items.append(item)

    content = [i.text for i in items if isinstance(i, ContentDelta)]
    tool_deltas = [i for i in items if isinstance(i, ToolCallsDelta)]
    usages = [i for i in items if isinstance(i, UsageInfo)]
    assert content == ["Hel", "lo"]
    assert tool_deltas == []
    assert usages == [UsageInfo(prompt_tokens=12, completion_tokens=2)]


@pytest.mark.asyncio
async def test_stream_call_with_tools_two_calls_ordered_by_index():
    """Two tool calls assembled across chunks are ordered by streamed index."""
    chunks = [
        _tool_chunk(
            tool_calls=[_tc_fragment(0, call_id="c1", name="get_user_profile", arguments="{}")]
        ),
        _tool_chunk(
            tool_calls=[_tc_fragment(1, call_id="c2", name="list_categories", arguments="{}")]
        ),
        _tool_chunk(finish_reason="tool_calls"),
    ]
    final_chunk = MagicMock()
    final_chunk.choices = []
    final_chunk.usage = MagicMock(prompt_tokens=20, completion_tokens=2)
    chunks.append(final_chunk)

    async def _async_iter():
        for chunk in chunks:
            yield chunk

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_async_iter())
    gateway = _fake_gateway(mock_client)

    items = []
    async for item in OpenAIGateway.stream_call_with_tools(
        gateway,
        endpoint="chat",
        messages=[{"role": "user", "content": "Hi"}],
        model="gpt-4o-mini",
        temperature=0.4,
        max_tokens=800,
        tools=[{"type": "function"}],
    ):
        items.append(item)

    tool_deltas = [i for i in items if isinstance(i, ToolCallsDelta)]
    assert len(tool_deltas) == 1
    assert [c["id"] for c in tool_deltas[0].tool_calls] == ["c1", "c2"]
