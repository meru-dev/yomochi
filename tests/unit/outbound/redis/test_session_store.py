"""Unit tests for RedisSessionStore — Fix 2: batched mget in list_active."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.domain.value_objects.ids import SessionId, UserId
from app.outbound.adapters.redis.session_store import RedisSessionStore

pytestmark = pytest.mark.asyncio

_UID = UserId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
_SID1 = SessionId(UUID("11111111-1111-1111-1111-111111111111"))
_SID2 = SessionId(UUID("22222222-2222-2222-2222-222222222222"))


def _future_ts(minutes: int = 60) -> float:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).timestamp()


def _session_json(sid: SessionId, uid: UserId, minutes: int = 60) -> bytes:
    expires = datetime.now(UTC) + timedelta(minutes=minutes)
    return json.dumps(
        {
            "id_": str(sid.value),
            "user_id": str(uid.value),
            "expires_at": expires.isoformat(),
            "user_agent": "test-agent",
            "ip": "127.0.0.1",
        }
    ).encode()


def _make_redis(
    zrangebyscore_result: list[bytes],
    mget_result: list[bytes | None],
) -> MagicMock:
    redis = MagicMock()
    redis.zrangebyscore = AsyncMock(return_value=zrangebyscore_result)
    redis.mget = AsyncMock(return_value=mget_result)
    # pipeline mock for save/revoke (not exercised here)
    pipe_ctx = MagicMock()
    pipe_ctx.__aenter__ = AsyncMock(return_value=pipe_ctx)
    pipe_ctx.__aexit__ = AsyncMock(return_value=False)
    pipe_ctx.execute = AsyncMock(return_value=[])
    redis.pipeline = MagicMock(return_value=pipe_ctx)
    return redis


async def test_list_active_uses_single_mget_call() -> None:
    """list_active must fetch all session keys in one mget round-trip."""
    sids_bytes = [str(_SID1.value).encode(), str(_SID2.value).encode()]
    raws = [_session_json(_SID1, _UID), _session_json(_SID2, _UID)]
    redis = _make_redis(sids_bytes, raws)
    store = RedisSessionStore(redis)

    sessions = await store.list_active(_UID)

    # Exactly one mget call with both keys
    redis.mget.assert_awaited_once()
    mget_args = redis.mget.call_args
    # keys passed positionally
    called_keys = list(mget_args.args)
    assert f"session:{_SID1.value}" in called_keys
    assert f"session:{_SID2.value}" in called_keys
    assert len(sessions) == 2


async def test_list_active_no_individual_get_calls() -> None:
    """Ensure no per-session .get() calls are made."""
    sids_bytes = [str(_SID1.value).encode()]
    redis = _make_redis(sids_bytes, [_session_json(_SID1, _UID)])
    redis.get = AsyncMock(return_value=None)  # should never be called
    store = RedisSessionStore(redis)

    await store.list_active(_UID)

    redis.get.assert_not_awaited()


async def test_list_active_skips_none_entries() -> None:
    """None entries from mget (key expired in Redis) are filtered out."""
    sids_bytes = [str(_SID1.value).encode(), str(_SID2.value).encode()]
    # Second entry is None — key already expired in Redis
    redis = _make_redis(sids_bytes, [_session_json(_SID1, _UID), None])
    store = RedisSessionStore(redis)

    sessions = await store.list_active(_UID)

    assert len(sessions) == 1
    assert sessions[0].id_ == _SID1


async def test_list_active_returns_empty_when_no_active_sids() -> None:
    """If zrangebyscore returns empty, skip mget entirely and return empty list."""
    redis = _make_redis([], [])
    store = RedisSessionStore(redis)

    sessions = await store.list_active(_UID)

    assert sessions == []
    redis.mget.assert_not_awaited()


async def test_list_active_deserializes_session_fields() -> None:
    sids_bytes = [str(_SID1.value).encode()]
    redis = _make_redis(sids_bytes, [_session_json(_SID1, _UID)])
    store = RedisSessionStore(redis)

    sessions = await store.list_active(_UID)

    assert sessions[0].id_ == _SID1
    assert sessions[0].user_id == _UID
    assert sessions[0].user_agent == "test-agent"
    assert sessions[0].ip == "127.0.0.1"
