import asyncio
import contextlib
import hashlib
import json
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_METHODS = frozenset({"POST", "PUT", "PATCH"})
_HEADER = "Idempotency-Key"
_LOCK_TTL_SECONDS = 30
_LOCK_POLL_INTERVAL_SECONDS = 0.1
_LOCK_MAX_POLLS = 50  # 5 s total wait


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: object,
        *,
        redis: Redis,  # type: ignore[type-arg]
        ttl: int = 86400,
        cookie_name: str = "auth",
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._redis = redis
        self._ttl = ttl
        self._cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next: object) -> Response:
        _call_next: Callable[[Request], Awaitable[Response]] = call_next  # type: ignore[assignment]
        key = request.headers.get(_HEADER)
        if key is None or request.method not in _METHODS:
            return await _call_next(request)

        # Identity is resolved by Dishka per-request, AFTER the middleware chain runs,
        # so request.state.user_id is unavailable here. Scope by the auth session cookie
        # instead (sha256'd so raw token never appears in Redis keys). Unauthenticated
        # requests share the "anon" scope — acceptable because idempotency for anon
        # POSTs is rare and same-scope collisions only leak between anon callers, not
        # across authenticated users.
        session_cookie = request.cookies.get(self._cookie_name)
        if session_cookie:
            session_scope = hashlib.sha256(session_cookie.encode()).hexdigest()
        else:
            session_scope = "anon"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        cache_key = f"idempotency:{session_scope}:{key_hash}"
        lock_key = f"idempotency:lock:{session_scope}:{key_hash}"

        try:
            # Fast path: response already cached.
            cached = await self._redis.get(cache_key)
            if cached is not None:
                return _decode_cached(cached)

            # Try to acquire the processing lock.
            acquired = await self._redis.set(lock_key, b"1", nx=True, ex=_LOCK_TTL_SECONDS)
        except RedisError:
            # Redis unavailable — degrade gracefully, process without idempotency.
            return await _call_next(request)

        if not acquired:
            # Another request holds the lock. Poll for its cached result.
            try:
                for _ in range(_LOCK_MAX_POLLS):
                    await asyncio.sleep(_LOCK_POLL_INTERVAL_SECONDS)
                    cached = await self._redis.get(cache_key)
                    if cached is not None:
                        return _decode_cached(cached)
            except RedisError:
                pass
            # Timed out or Redis error — fall through and process.
            return await _call_next(request)

        # We hold the lock. Execute the handler, cache the result, release.
        try:
            response = await _call_next(request)
            body_chunks = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
            body = b"".join(body_chunks)

            # Cache only successful responses; 4xx/5xx must not be pinned for the
            # full TTL (transient 5xx would otherwise replay errors for 24 h).
            if 200 <= response.status_code < 300:
                with contextlib.suppress(RedisError):
                    await self._redis.setex(
                        cache_key,
                        self._ttl,
                        json.dumps(
                            {
                                "body": body.decode("utf-8", errors="replace"),
                                "status": response.status_code,
                                "media_type": response.media_type,
                            }
                        ),
                    )

            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        finally:
            with contextlib.suppress(RedisError):
                await self._redis.delete(lock_key)


def _decode_cached(raw: bytes) -> Response:
    data = json.loads(raw)
    body_str: str | None = data.get("body")
    return Response(
        content=body_str.encode() if body_str else b"",
        status_code=data["status"],
        media_type=data.get("media_type"),
    )
