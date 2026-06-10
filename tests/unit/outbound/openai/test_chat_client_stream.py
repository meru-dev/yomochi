from unittest.mock import MagicMock

import pytest

from app.application.chat.ports.chat_ai_client import ChatRequest
from app.outbound.adapters.openai.chat_client import OpenAIChatClient


@pytest.mark.asyncio
async def test_stream_delegates_to_gateway_stream_call():
    """OpenAIChatClient.stream() should yield tokens from gateway.stream_call()."""

    async def fake_stream_call(**kwargs):
        for t in ["tok1", "tok2"]:
            yield t

    mock_gateway = MagicMock()
    mock_gateway.stream_call = fake_stream_call

    client = OpenAIChatClient(
        gateway=mock_gateway,
        model="gpt-4o-mini",
        read_timeout_seconds=30.0,
    )

    request = ChatRequest(message="hello", chunks=[], history=[])
    tokens = [t async for t in client.stream(request)]
    assert tokens == ["tok1", "tok2"]
