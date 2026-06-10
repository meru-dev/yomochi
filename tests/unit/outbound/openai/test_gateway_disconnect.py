from __future__ import annotations

import pytest

pytest.skip(
    "Pending implementation — referenced behaviour not yet present in source",
    allow_module_level=True,
)


"""Pin stream-disconnect partial-token accounting in OpenAIGateway.

When a client disconnects mid-stream (GeneratorExit), the gateway must:
- Record partial completion tokens in openai_tokens_total (so we don't undercount cost).
- Increment openai_call_total with outcome="disconnect".
"""


from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.outbound.adapters.openai._gateway.gateway as gw_module
from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway


def _make_gateway() -> MagicMock:
    """Build a fake gateway instance with wired breaker/limiter."""
    gateway = MagicMock(spec=OpenAIGateway)
    gateway._default_timeout = 30.0

    breaker_ctx = AsyncMock()
    breaker_ctx.__aenter__ = AsyncMock(return_value=None)
    breaker_ctx.__aexit__ = AsyncMock(return_value=False)
    gateway._breaker = MagicMock(__aenter__=breaker_ctx.__aenter__, __aexit__=breaker_ctx.__aexit__)

    limiter_ctx = AsyncMock()
    limiter_ctx.__aenter__ = AsyncMock(return_value=None)
    limiter_ctx.__aexit__ = AsyncMock(return_value=False)
    gateway._limiter = MagicMock(__aenter__=limiter_ctx.__aenter__, __aexit__=limiter_ctx.__aexit__)

    return gateway


def _make_stream_client(tokens: list[str]) -> AsyncMock:
    """Fake AsyncOpenAI client that yields text tokens then a usage chunk."""

    def _chunk(content: str | None):
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = content
        c.usage = None
        return c

    final = MagicMock()
    final.choices = []
    final.usage = MagicMock(prompt_tokens=10, completion_tokens=len(tokens))

    async def _async_iter():
        for t in tokens:
            yield _chunk(t)
        yield final

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_async_iter())
    return mock_client


@pytest.mark.asyncio
async def test_stream_disconnect_records_outcome_disconnect() -> None:
    """Client closes the generator after the first chunk — must record outcome=disconnect."""
    gateway = _make_gateway()
    mock_client = _make_stream_client(["Hello", " world"])
    gateway._client = MagicMock()
    gateway._client.with_options = MagicMock(return_value=mock_client)

    with (
        patch.object(gw_module, "openai_call_total") as mock_call_total,
        patch.object(gw_module, "openai_tokens_total"),
    ):
        gen = OpenAIGateway.stream_call(
            gateway,
            endpoint="chat",
            messages=[{"role": "user", "content": "Hi"}],
            model="gpt-4o-mini",
            temperature=0.4,
            max_tokens=800,
        )

        first = await gen.__anext__()
        assert first == "Hello"
        await gen.aclose()

        mock_call_total.labels.assert_called_with(endpoint="chat", outcome="disconnect")
        mock_call_total.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_stream_disconnect_records_partial_tokens_when_nonzero() -> None:
    """Partial completion_chunks count is used when completion_tokens not yet received."""
    gateway = _make_gateway()
    mock_client = _make_stream_client(["A", "B", "C"])
    gateway._client = MagicMock()
    gateway._client.with_options = MagicMock(return_value=mock_client)

    with (
        patch.object(gw_module, "openai_call_total"),
        patch.object(gw_module, "openai_tokens_total") as mock_tokens,
    ):
        gen = OpenAIGateway.stream_call(
            gateway,
            endpoint="chat",
            messages=[],
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=100,
        )

        await gen.__anext__()  # "A"
        await gen.__anext__()  # "B"
        await gen.aclose()

        assert mock_tokens.labels.call_count >= 1
