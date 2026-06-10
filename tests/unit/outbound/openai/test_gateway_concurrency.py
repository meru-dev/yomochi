from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiolimiter import AsyncLimiter

import app.outbound.adapters.openai._gateway.gateway as gw_module
from app.application.common.ai_errors import OpenAICallError
from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway


def _make_breakers() -> dict:
    breaker = AsyncMock()
    breaker.__aenter__ = AsyncMock(return_value=None)
    breaker.__aexit__ = AsyncMock(return_value=False)
    breaker.context = MagicMock()
    breaker.context.state = "closed"
    return {"chat": breaker, "embeddings": breaker, "vision": breaker}


def _make_gateway(limiter: AsyncLimiter | None = None) -> OpenAIGateway:
    mock_client = AsyncMock()
    mock_client.with_options = MagicMock(return_value=mock_client)

    return OpenAIGateway(
        client=mock_client,
        limiter=limiter or AsyncLimiter(max_rate=1000, time_period=60),
        breakers=_make_breakers(),
        default_read_timeout_seconds=5.0,
    )


@pytest.mark.asyncio
async def test_limiter_entered_once_per_call() -> None:
    """Each gateway.call() must acquire the limiter exactly once."""
    gateway = _make_gateway()
    enter_count = 0
    real_limiter = gateway._limiter
    original_aenter = type(real_limiter).__aenter__

    async def counting_aenter(self):
        nonlocal enter_count
        enter_count += 1
        return await original_aenter(self)

    async def _fn(client):
        return "ok"

    # patch.object restores the class attribute on exit — no session-level pollution
    with (
        patch.object(type(real_limiter), "__aenter__", counting_aenter),
        patch.object(gw_module, "openai_call_total"),
        patch.object(gw_module, "openai_call_duration_seconds"),
    ):
        await gateway.call(endpoint="chat", fn=_fn)
        await gateway.call(endpoint="chat", fn=_fn)

    assert enter_count == 2, f"expected limiter acquired 2 times, got {enter_count}"


@pytest.mark.asyncio
async def test_limiter_throttles_excess_calls() -> None:
    """A 1-per-10s limiter must cause the second call to wait, not fail immediately.

    asyncio.wait_for cancels the task after 0.1s, causing CancelledError inside the
    limiter's acquire(). The gateway's BaseException handler translates that to
    OpenAICallError. Either way, the call does NOT return immediately — it blocks until
    cancelled.
    """
    limiter = AsyncLimiter(max_rate=1, time_period=10)
    gateway = _make_gateway(limiter)

    async def _fn(client):
        return "ok"

    with (
        patch.object(gw_module, "openai_call_total"),
        patch.object(gw_module, "openai_call_duration_seconds"),
    ):
        await gateway.call(endpoint="chat", fn=_fn)

        # The second call blocks in the limiter. wait_for cancels it, which surfaces as
        # OpenAICallError (CancelledError → map_exception → OpenAICallError).
        with pytest.raises((asyncio.TimeoutError, OpenAICallError)):
            await asyncio.wait_for(
                gateway.call(endpoint="chat", fn=_fn),
                timeout=0.1,
            )
