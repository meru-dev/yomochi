from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.domain.value_objects.ids import UserId
from app.outbound.adapters.redis.search_cache import RedisSearchCache

pytestmark = pytest.mark.asyncio

_USER_ID = UserId(UUID("11111111-1111-1111-1111-111111111111"))
_USER_ID_2 = UserId(UUID("22222222-2222-2222-2222-222222222222"))
_QUERY = "coffee shop"
_TTL = 300
_TX_IDS = [
    UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
]


def _mock_redis(get_result: bytes | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=get_result)
    redis.set = AsyncMock(return_value=True)
    return redis


def _expected_key(user_id: UserId, query: str) -> str:
    uid = str(user_id.value)
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    return f"search_cache:{uid}:{query_hash}"


# --- cache miss ---


async def test_get_returns_none_on_cache_miss() -> None:
    redis = _mock_redis(get_result=None)
    cache = RedisSearchCache(redis, ttl=_TTL)

    result = await cache.get(_USER_ID, _QUERY)

    assert result is None


async def test_get_increments_miss_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.outbound.adapters.redis.search_cache as module

    inc_mock = MagicMock()
    monkeypatch.setattr(module.search_cache_misses_total, "inc", inc_mock)

    redis = _mock_redis(get_result=None)
    cache = RedisSearchCache(redis, ttl=_TTL)

    await cache.get(_USER_ID, _QUERY)

    inc_mock.assert_called_once()


# --- cache hit ---


async def test_get_returns_uuids_on_cache_hit() -> None:
    raw = json.dumps([str(tx_id) for tx_id in _TX_IDS]).encode()
    redis = _mock_redis(get_result=raw)
    cache = RedisSearchCache(redis, ttl=_TTL)

    result = await cache.get(_USER_ID, _QUERY)

    assert result == _TX_IDS


async def test_get_increments_hit_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.outbound.adapters.redis.search_cache as module

    inc_mock = MagicMock()
    monkeypatch.setattr(module.search_cache_hits_total, "inc", inc_mock)

    raw = json.dumps([str(tx_id) for tx_id in _TX_IDS]).encode()
    redis = _mock_redis(get_result=raw)
    cache = RedisSearchCache(redis, ttl=_TTL)

    await cache.get(_USER_ID, _QUERY)

    inc_mock.assert_called_once()


# --- set ---


async def test_set_stores_json_with_ttl() -> None:
    redis = _mock_redis()
    cache = RedisSearchCache(redis, ttl=_TTL)

    await cache.set(_USER_ID, _QUERY, _TX_IDS)

    expected_key = _expected_key(_USER_ID, _QUERY)
    expected_data = json.dumps([str(tx_id) for tx_id in _TX_IDS])
    redis.set.assert_awaited_once_with(expected_key, expected_data, ex=_TTL)


# --- round-trip ---


async def test_set_and_get_round_trip() -> None:
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)

    stored: dict[str, bytes] = {}

    async def fake_set(key: str, value: str, *, ex: int) -> None:
        stored[key] = value.encode() if isinstance(value, str) else value

    async def fake_get(key: str) -> bytes | None:
        return stored.get(key)

    redis.set = fake_set
    redis.get = fake_get

    cache = RedisSearchCache(redis, ttl=_TTL)

    await cache.set(_USER_ID, _QUERY, _TX_IDS)
    result = await cache.get(_USER_ID, _QUERY)

    assert result == _TX_IDS


# --- user-scoped keys ---


async def test_cache_key_is_user_scoped() -> None:
    redis = _mock_redis(get_result=None)
    cache = RedisSearchCache(redis, ttl=_TTL)

    await cache.get(_USER_ID, _QUERY)
    await cache.get(_USER_ID_2, _QUERY)

    calls = [call.args[0] for call in redis.get.await_args_list]
    assert calls[0] != calls[1]
    assert str(_USER_ID.value) in calls[0]
    assert str(_USER_ID_2.value) in calls[1]


# --- empty list round-trip ---


async def test_empty_list_round_trip() -> None:
    redis = MagicMock()

    stored: dict[str, bytes] = {}

    async def fake_set(key: str, value: str, *, ex: int) -> None:
        stored[key] = value.encode() if isinstance(value, str) else value

    async def fake_get(key: str) -> bytes | None:
        return stored.get(key)

    redis.set = fake_set
    redis.get = fake_get

    cache = RedisSearchCache(redis, ttl=_TTL)

    await cache.set(_USER_ID, _QUERY, [])
    result = await cache.get(_USER_ID, _QUERY)

    assert result == []
    assert result is not None
