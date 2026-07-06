from unittest.mock import MagicMock

import pytest
from aiolimiter import AsyncLimiter
from openai import AsyncOpenAI

from app.application.common.ai_errors import OpenAICallError


@pytest.mark.asyncio
async def test_vision_failure_does_not_open_chat_breaker() -> None:
    """Repeated vision failures must not open the chat circuit breaker (per-class
    breaker isolation)."""
    import purgatory

    from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway

    factory = purgatory.AsyncCircuitBreakerFactory(default_threshold=2, default_ttl=60)
    chat_breaker = await factory.get_breaker("chat")
    vision_breaker = await factory.get_breaker("vision")
    parse_breaker = await factory.get_breaker("parse")

    client = MagicMock(spec=AsyncOpenAI)

    def _limiter() -> AsyncLimiter:
        return AsyncLimiter(max_rate=100, time_period=60)

    gateway = OpenAIGateway(
        client=client,
        limiters={"chat": _limiter(), "vision": _limiter(), "parse": _limiter()},
        breakers={"chat": chat_breaker, "vision": vision_breaker, "parse": parse_breaker},
        default_read_timeout_seconds=30.0,
    )

    # Trigger vision failures up to the threshold
    async def _fail(_c):
        raise RuntimeError("vision down")

    for _ in range(2):
        with pytest.raises(OpenAICallError):
            await gateway.call(endpoint="vision", fn=_fail)

    # Chat breaker must still be closed
    assert chat_breaker.context.state == "closed", (
        f"chat breaker opened due to vision failures: {chat_breaker.context.state}"
    )
