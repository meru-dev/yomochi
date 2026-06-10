from unittest.mock import MagicMock

import pytest
from aiolimiter import AsyncLimiter
from openai import AsyncOpenAI

from app.application.common.ai_errors import OpenAICallError


@pytest.mark.asyncio
async def test_embedding_failure_does_not_open_chat_breaker() -> None:
    """Repeated embedding failures must not open the chat circuit breaker."""
    import purgatory

    from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway

    factory = purgatory.AsyncCircuitBreakerFactory(default_threshold=2, default_ttl=60)
    chat_breaker = await factory.get_breaker("chat")
    embedding_breaker = await factory.get_breaker("embeddings")

    client = MagicMock(spec=AsyncOpenAI)
    limiter = AsyncLimiter(max_rate=100, time_period=60)

    gateway = OpenAIGateway(
        client=client,
        limiter=limiter,
        breakers={"chat": chat_breaker, "embeddings": embedding_breaker, "vision": chat_breaker},
        default_read_timeout_seconds=30.0,
    )

    # Trigger embedding failures up to the threshold
    async def _fail(_c):
        raise RuntimeError("embedding down")

    for _ in range(2):
        with pytest.raises(OpenAICallError):
            await gateway.call(endpoint="embeddings", fn=_fail)

    # Chat breaker must still be closed
    assert chat_breaker.context.state == "closed", (
        f"chat breaker opened due to embedding failures: {chat_breaker.context.state}"
    )
