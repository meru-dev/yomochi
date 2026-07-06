from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.inbound.http.middleware.idempotency import IdempotencyMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request


def _make_redis(*, get_return=None, set_nx_return: bool = True):
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=get_return)
    redis.set = AsyncMock(return_value=set_nx_return)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    return redis


async def _app_handler(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _make_app(redis):
    app = Starlette(routes=[Route("/", _app_handler, methods=["POST"])])
    app.add_middleware(IdempotencyMiddleware, redis=redis)
    return app


def test_idempotency_key_includes_user_id():
    """Redis cache key must be scoped per user to prevent cross-user cache collision."""
    redis = _make_redis()
    app = _make_app(redis)
    client = TestClient(app, raise_server_exceptions=True)

    client.post("/", headers={"Idempotency-Key": "same-key"})

    # Verify at least one GET was called with a cache key (not the lock key)
    get_calls = redis.get.call_args_list
    cache_calls = [c for c in get_calls if "idempotency:anon:" in str(c)]
    assert len(cache_calls) >= 1
    parts = cache_calls[0][0][0].split(":")
    assert len(parts) >= 3
    assert parts[1] == "anon"


def test_cached_response_returned_without_executing_handler():
    cached_payload = json.dumps(
        {"body": '{"ok": true}', "status": 200, "media_type": "application/json"}
    ).encode()
    redis = _make_redis(get_return=cached_payload)
    execute_count = 0

    async def counting_handler(request: Request) -> JSONResponse:
        nonlocal execute_count
        execute_count += 1
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/", counting_handler, methods=["POST"])])
    app.add_middleware(IdempotencyMiddleware, redis=redis)
    client = TestClient(app, raise_server_exceptions=True)

    client.post("/", headers={"Idempotency-Key": "cached-key"})

    assert execute_count == 0


def test_lock_acquired_before_executing_handler():
    """When cache is empty, SET NX lock must be acquired before handler runs."""
    redis = _make_redis(set_nx_return=True)

    handler_saw_set_call = False

    async def spy_handler(request: Request) -> JSONResponse:
        nonlocal handler_saw_set_call
        handler_saw_set_call = redis.set.await_count >= 1
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/", spy_handler, methods=["POST"])])
    app.add_middleware(IdempotencyMiddleware, redis=redis)
    client = TestClient(app, raise_server_exceptions=True)

    client.post("/", headers={"Idempotency-Key": "new-key"})

    assert handler_saw_set_call, "SET NX lock not called before handler ran"
    set_kwargs = [c[1] for c in redis.set.call_args_list]
    assert any(kw.get("nx") is True for kw in set_kwargs), "No SET NX call found"


def test_lock_released_after_response():
    redis = _make_redis(set_nx_return=True)
    app = _make_app(redis)
    client = TestClient(app, raise_server_exceptions=True)

    client.post("/", headers={"Idempotency-Key": "lock-release-key"})

    redis.delete.assert_awaited_once()


def test_no_key_header_bypasses_middleware():
    redis = _make_redis()
    app = _make_app(redis)
    client = TestClient(app, raise_server_exceptions=True)

    client.post("/")

    redis.get.assert_not_awaited()
    redis.set.assert_not_awaited()


def test_get_request_bypasses_middleware():
    async def get_handler(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    redis = _make_redis()
    app = Starlette(routes=[Route("/", get_handler, methods=["GET"])])
    app.add_middleware(IdempotencyMiddleware, redis=redis)
    client = TestClient(app, raise_server_exceptions=True)

    client.get("/", headers={"Idempotency-Key": "some-key"})

    redis.get.assert_not_awaited()
