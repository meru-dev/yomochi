from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import purgatory
import pytest
from aiolimiter import AsyncLimiter

from app.application.common.ai_errors import (
    AIInvalidRequestError,
    AIRateLimitedError,
    AITimeoutError,
    AIUnavailableError,
)
from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway

pytestmark = pytest.mark.asyncio


def _client_with_options_passthrough() -> MagicMock:
    """Returns a MagicMock AsyncOpenAI whose with_options(...) returns itself."""
    client = MagicMock()
    client.with_options = MagicMock(return_value=client)
    return client


async def _new_breakers(threshold: int = 5, ttl: int = 60) -> dict:
    factory = purgatory.AsyncCircuitBreakerFactory(default_threshold=threshold, default_ttl=ttl)
    return {
        endpoint: await factory.get_breaker(f"test_{endpoint}")
        for endpoint in ("chat", "embeddings", "vision")
    }


async def test_call_returns_fn_result_on_success() -> None:
    client = _client_with_options_passthrough()
    gateway = OpenAIGateway(
        client=client,
        limiter=AsyncLimiter(max_rate=100, time_period=60),
        breakers=await _new_breakers(),
        default_read_timeout_seconds=10.0,
    )

    result = await gateway.call(
        endpoint="chat",
        fn=AsyncMock(return_value="ok"),
    )

    assert result == "ok"


async def test_call_applies_per_call_timeout_to_client() -> None:
    client = _client_with_options_passthrough()
    gateway = OpenAIGateway(
        client=client,
        limiter=AsyncLimiter(max_rate=100, time_period=60),
        breakers=await _new_breakers(),
        default_read_timeout_seconds=10.0,
    )

    fn = AsyncMock(return_value="x")
    await gateway.call(endpoint="embeddings", fn=fn, timeout=3.0)

    # with_options called at init (default timeout) + once for explicit timeout
    calls = list(client.with_options.call_args_list)
    assert any(c == (((), {"timeout": 3.0}),) or c.kwargs == {"timeout": 3.0} for c in calls)
    fn.assert_awaited_once_with(client)


async def test_call_falls_back_to_default_timeout() -> None:
    client = _client_with_options_passthrough()
    gateway = OpenAIGateway(
        client=client,
        limiter=AsyncLimiter(max_rate=100, time_period=60),
        breakers=await _new_breakers(),
        default_read_timeout_seconds=42.0,
    )

    await gateway.call(endpoint="chat", fn=AsyncMock(return_value="x"))

    # with_options called once at init with default timeout — no second call for no-timeout call
    client.with_options.assert_called_once_with(timeout=42.0)


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (
            openai.APITimeoutError(httpx.Request("POST", "https://x")),
            AITimeoutError,
        ),
        (
            openai.APIConnectionError(request=httpx.Request("POST", "https://x")),
            AIUnavailableError,
        ),
    ],
)
async def test_call_translates_sdk_exceptions(
    raised: BaseException, expected: type[BaseException]
) -> None:
    client = _client_with_options_passthrough()
    gateway = OpenAIGateway(
        client=client,
        limiter=AsyncLimiter(max_rate=100, time_period=60),
        breakers=await _new_breakers(),
        default_read_timeout_seconds=10.0,
    )

    with pytest.raises(expected):
        await gateway.call(endpoint="chat", fn=AsyncMock(side_effect=raised))


async def test_call_translates_rate_limit_error() -> None:
    response = httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat"),
    )
    raised = openai.RateLimitError(message="rl", response=response, body={"error": "rl"})

    client = _client_with_options_passthrough()
    gateway = OpenAIGateway(
        client=client,
        limiter=AsyncLimiter(max_rate=100, time_period=60),
        breakers=await _new_breakers(),
        default_read_timeout_seconds=10.0,
    )

    with pytest.raises(AIRateLimitedError):
        await gateway.call(endpoint="chat", fn=AsyncMock(side_effect=raised))


async def test_call_translates_bad_request_to_invalid() -> None:
    response = httpx.Response(
        status_code=400,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat"),
    )
    raised = openai.BadRequestError(message="br", response=response, body={"error": "br"})
    client = _client_with_options_passthrough()
    gateway = OpenAIGateway(
        client=client,
        limiter=AsyncLimiter(max_rate=100, time_period=60),
        breakers=await _new_breakers(),
        default_read_timeout_seconds=10.0,
    )

    with pytest.raises(AIInvalidRequestError):
        await gateway.call(endpoint="chat", fn=AsyncMock(side_effect=raised))


async def test_circuit_breaker_opens_after_threshold_failures() -> None:
    breakers = await _new_breakers(threshold=2, ttl=60)
    client = _client_with_options_passthrough()
    gateway = OpenAIGateway(
        client=client,
        limiter=AsyncLimiter(max_rate=100, time_period=60),
        breakers=breakers,
        default_read_timeout_seconds=10.0,
    )

    failing_fn = AsyncMock(
        side_effect=openai.APIConnectionError(request=httpx.Request("POST", "https://x"))
    )

    # Two failures trip the breaker.
    for _ in range(2):
        with pytest.raises(AIUnavailableError):
            await gateway.call(endpoint="chat", fn=failing_fn)

    # The next call should fast-fail without invoking fn.
    fresh_fn = AsyncMock(return_value="never")
    with pytest.raises(AIUnavailableError):
        await gateway.call(endpoint="chat", fn=fresh_fn)
    fresh_fn.assert_not_awaited()
