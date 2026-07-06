"""Unit tests for RedisConsumerIdempotencyStore — Fix 1: atomic INCR+EXPIRE via Lua."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.outbound.adapters.redis.consumer_idempotency_store import (
    _FAILURE_TTL,
    RedisConsumerIdempotencyStore,
)

pytestmark = pytest.mark.asyncio


def _make_store(script_return: int = 1) -> tuple[RedisConsumerIdempotencyStore, MagicMock]:
    """Build a store with a mocked Redis that returns script_return from the Lua script."""
    mock_script = AsyncMock(return_value=script_return)
    redis = MagicMock()
    redis.register_script = MagicMock(return_value=mock_script)
    redis.exists = AsyncMock(return_value=0)
    redis.set = AsyncMock(return_value=True)
    store = RedisConsumerIdempotencyStore(redis)
    return store, mock_script


async def test_increment_failures_returns_count() -> None:
    store, _ = _make_store(script_return=1)
    result = await store.increment_failures("evt-001")
    assert result == 1


async def test_increment_failures_returns_increasing_count() -> None:
    mock_script = AsyncMock(side_effect=[1, 2, 3])
    redis = MagicMock()
    redis.register_script = MagicMock(return_value=mock_script)
    store = RedisConsumerIdempotencyStore(redis)

    counts = [await store.increment_failures("evt-abc") for _ in range(3)]
    assert counts == [1, 2, 3]


async def test_increment_failures_calls_lua_script_with_correct_key_and_ttl() -> None:
    store, mock_script = _make_store(script_return=1)
    await store.increment_failures("evt-xyz")

    mock_script.assert_awaited_once_with(
        keys=["consumer:failures:evt-xyz"],
        args=[_FAILURE_TTL],
    )


async def test_increment_failures_uses_lua_not_separate_incr_expire() -> None:
    """Verify no separate incr/expire calls — atomicity is via Lua script only."""
    store, mock_script = _make_store(script_return=1)
    redis = store._redis

    await store.increment_failures("evt-atomic")

    # The script was called
    mock_script.assert_awaited_once()
    # No separate INCR or EXPIRE calls
    redis.incr.assert_not_called()
    redis.expire.assert_not_called()


async def test_is_processed_delegates_to_exists() -> None:
    mock_script = AsyncMock(return_value=1)
    redis = MagicMock()
    redis.register_script = MagicMock(return_value=mock_script)
    redis.exists = AsyncMock(return_value=1)
    store = RedisConsumerIdempotencyStore(redis)

    result = await store.is_processed("evt-processed")

    redis.exists.assert_awaited_once_with("consumer:idempotency:evt-processed")
    assert result is True


async def test_mark_processed_uses_set_with_ttl() -> None:
    mock_script = AsyncMock(return_value=1)
    redis = MagicMock()
    redis.register_script = MagicMock(return_value=mock_script)
    redis.set = AsyncMock(return_value=True)
    store = RedisConsumerIdempotencyStore(redis)

    await store.mark_processed("evt-mark", ttl_seconds=3600)

    redis.set.assert_awaited_once_with("consumer:idempotency:evt-mark", "1", ex=3600)
