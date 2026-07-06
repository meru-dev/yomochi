"""Per-endpoint-class limiter buckets + bounded-queue overflow rejection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiolimiter import AsyncLimiter

from app.application.common.ai_errors import AIRateLimitedError
from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway
from app.outbound.observability.prometheus import openai_limiter_rejected_total

pytestmark = pytest.mark.asyncio


def _breaker() -> MagicMock:
    breaker = AsyncMock()
    breaker.__aenter__ = AsyncMock(return_value=None)
    breaker.__aexit__ = AsyncMock(return_value=False)
    breaker.context = MagicMock()
    breaker.context.state = "closed"
    return breaker


def _make_gateway(max_queue: int = 64) -> OpenAIGateway:
    client = MagicMock()
    client.with_options = MagicMock(return_value=client)
    # Distinct limiter instance per endpoint so we can prove isolation.
    limiters = {
        ep: AsyncLimiter(max_rate=1000, time_period=60) for ep in ("chat", "vision", "parse")
    }
    breakers = {ep: _breaker() for ep in ("chat", "vision", "parse")}
    return OpenAIGateway(
        client=client,
        limiters=limiters,
        breakers=breakers,
        default_read_timeout_seconds=5.0,
        max_queue=max_queue,
    )


async def test_each_endpoint_uses_its_own_bucket() -> None:
    """A call on one endpoint only acquires that endpoint's limiter (isolation)."""
    gateway = _make_gateway()
    # Swap in mock limiters so we can assert exactly which bucket was acquired.
    mock_limiters = {ep: MagicMock(acquire=AsyncMock()) for ep in ("chat", "vision", "parse")}
    gateway._limiters = mock_limiters

    await gateway.call(endpoint="vision", fn=AsyncMock(return_value="ok"))

    mock_limiters["vision"].acquire.assert_awaited_once()
    mock_limiters["chat"].acquire.assert_not_awaited()
    mock_limiters["parse"].acquire.assert_not_awaited()


async def test_overflow_is_rejected_fast_with_metric() -> None:
    """When the waiter queue for a bucket is full, the call is rejected immediately
    (AIRateLimitedError) without invoking fn, and the reject counter increments."""
    gateway = _make_gateway(max_queue=2)
    # Simulate a saturated waiter queue for the chat bucket.
    gateway._waiting["chat"] = 2

    rejected = openai_limiter_rejected_total.labels(endpoint="chat")
    before = rejected._value.get()  # type: ignore[attr-defined]

    fn = AsyncMock(return_value="never")
    with pytest.raises(AIRateLimitedError):
        await gateway.call(endpoint="chat", fn=fn)

    fn.assert_not_awaited()
    assert rejected._value.get() - before == 1  # type: ignore[attr-defined]
    # Other buckets remain unaffected.
    assert gateway._waiting["vision"] == 0
