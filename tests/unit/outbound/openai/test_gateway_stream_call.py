from unittest.mock import AsyncMock, MagicMock

import pytest

from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway, UsageInfo


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
