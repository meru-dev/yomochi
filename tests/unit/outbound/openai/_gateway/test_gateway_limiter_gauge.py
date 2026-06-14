"""Unit tests for openai_limiter_waiting gauge — Fix 5."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiolimiter import AsyncLimiter

import app.outbound.adapters.openai._gateway.gateway as gw_module
from app.application.common.ai_errors import OpenAICallError
from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway

pytestmark = pytest.mark.asyncio


def _make_breakers() -> dict:
    breaker = AsyncMock()
    breaker.__aenter__ = AsyncMock(return_value=None)
    breaker.__aexit__ = AsyncMock(return_value=False)
    breaker.context = MagicMock()
    breaker.context.state = "closed"
    return {"chat": breaker, "embeddings": breaker, "vision": breaker}


def _make_gateway(limiter: AsyncLimiter | None = None) -> OpenAIGateway:
    mock_client = MagicMock()
    mock_client.with_options = MagicMock(return_value=mock_client)
    return OpenAIGateway(
        client=mock_client,
        limiter=limiter or AsyncLimiter(max_rate=1000, time_period=60),
        breakers=_make_breakers(),
        default_read_timeout_seconds=5.0,
    )


async def test_gauge_incremented_before_acquire_and_decremented_after() -> None:
    """openai_limiter_waiting must be inc() before acquire and dec() after."""
    gateway = _make_gateway()

    gauge_mock = MagicMock()
    gauge_labels_mock = MagicMock()
    gauge_mock.labels = MagicMock(return_value=gauge_labels_mock)

    with (
        patch.object(gw_module, "openai_limiter_waiting", gauge_mock),
        patch.object(gw_module, "openai_call_total"),
        patch.object(gw_module, "openai_call_duration_seconds"),
    ):
        await gateway.call(endpoint="chat", fn=AsyncMock(return_value="ok"))

    gauge_mock.labels.assert_called_with(endpoint="chat")
    gauge_labels_mock.inc.assert_called_once()
    gauge_labels_mock.dec.assert_called_once()


async def test_gauge_decremented_even_on_acquire_cancellation() -> None:
    """If acquire() is cancelled, the gauge must still be decremented (finally block)."""
    gateway = _make_gateway()

    gauge_mock = MagicMock()
    gauge_labels_mock = MagicMock()
    gauge_mock.labels = MagicMock(return_value=gauge_labels_mock)

    # Make acquire raise CancelledError to simulate cancellation during wait
    async def raising_acquire(self: AsyncLimiter) -> None:
        raise asyncio.CancelledError

    with (
        patch.object(gw_module, "openai_limiter_waiting", gauge_mock),
        patch.object(gw_module, "openai_call_total"),
        patch.object(gw_module, "openai_call_duration_seconds"),
        patch.object(type(gateway._limiter), "acquire", raising_acquire),
        pytest.raises(asyncio.CancelledError),
    ):
        await gateway.call(endpoint="chat", fn=AsyncMock(return_value="ok"))

    # Gauge was incremented, and despite cancellation, decremented in finally
    gauge_labels_mock.inc.assert_called_once()
    gauge_labels_mock.dec.assert_called_once()


async def test_gauge_decremented_on_fn_error() -> None:
    """If the wrapped fn raises, gauge must still be decremented."""
    gateway = _make_gateway()

    gauge_mock = MagicMock()
    gauge_labels_mock = MagicMock()
    gauge_mock.labels = MagicMock(return_value=gauge_labels_mock)

    with (
        patch.object(gw_module, "openai_limiter_waiting", gauge_mock),
        patch.object(gw_module, "openai_call_total"),
        patch.object(gw_module, "openai_call_duration_seconds"),
        pytest.raises(OpenAICallError),
    ):
        await gateway.call(
            endpoint="embeddings",
            fn=AsyncMock(side_effect=RuntimeError("boom")),
        )

    gauge_labels_mock.inc.assert_called_once()
    gauge_labels_mock.dec.assert_called_once()


async def test_gauge_label_matches_endpoint() -> None:
    """Label endpoint value must match the endpoint passed to call()."""
    gateway = _make_gateway()

    gauge_mock = MagicMock()
    gauge_labels_mock = MagicMock()
    gauge_mock.labels = MagicMock(return_value=gauge_labels_mock)

    with (
        patch.object(gw_module, "openai_limiter_waiting", gauge_mock),
        patch.object(gw_module, "openai_call_total"),
        patch.object(gw_module, "openai_call_duration_seconds"),
    ):
        await gateway.call(endpoint="embeddings", fn=AsyncMock(return_value=[]))

    gauge_mock.labels.assert_called_with(endpoint="embeddings")


async def test_stream_gauge_decremented_even_on_acquire_cancellation() -> None:
    """stream_call: if acquire() is cancelled, gauge must still be decremented (finally block)
    and CancelledError propagates raw (not wrapped as OpenAICallError)."""
    gateway = _make_gateway()

    gauge_mock = MagicMock()
    gauge_labels_mock = MagicMock()
    gauge_mock.labels = MagicMock(return_value=gauge_labels_mock)

    async def raising_acquire(self: AsyncLimiter) -> None:
        raise asyncio.CancelledError

    with (
        patch.object(gw_module, "openai_limiter_waiting", gauge_mock),
        patch.object(gw_module, "openai_call_total"),
        patch.object(type(gateway._limiter), "acquire", raising_acquire),
        pytest.raises(asyncio.CancelledError),
    ):
        # stream_call is an async generator; must be consumed to run body
        async for _ in gateway.stream_call(
            endpoint="chat",
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
            temperature=0.0,
            max_tokens=10,
        ):
            pass

    gauge_labels_mock.inc.assert_called_once()
    gauge_labels_mock.dec.assert_called_once()
