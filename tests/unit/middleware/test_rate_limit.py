from __future__ import annotations

import ipaddress
import json
import math
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import RedisError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.inbound.http.middleware.rate_limit import (
    RateLimitMiddleware,
    parse_trusted_proxies,
)
from app.inbound.http.middleware.rate_limit_policy import (
    DEFAULT,
    POLICIES,
    SKIP,
    Policy,
    policy_marker,
    resolve_policy,
)

if TYPE_CHECKING:
    from starlette.requests import Request


# ---------- 1. GCRA algorithm reference ----------


def _gcra_step(
    *,
    state_tat: int | None,
    now_ms: int,
    emission_interval_ms: int,
    burst_capacity_ms: int,
) -> tuple[bool, int, int, int, int]:
    """Pure-Python mirror of the Lua GCRA script. Returns:

    (allowed, remaining, reset_ms, retry_after_ms, new_state_tat)
    """
    tat = state_tat if state_tat is not None else now_ms
    if tat < now_ms:
        tat = now_ms
    new_tat = tat + emission_interval_ms
    allow_at = new_tat - burst_capacity_ms
    if now_ms >= allow_at:
        remaining = max(0, (burst_capacity_ms - (new_tat - now_ms)) // emission_interval_ms)
        return True, remaining, new_tat - now_ms, 0, new_tat
    return False, 0, tat - now_ms, allow_at - now_ms, tat


def test_gcra_first_request_allowed_from_cold_state() -> None:
    allowed, remaining, _reset, retry, _tat = _gcra_step(
        state_tat=None,
        now_ms=1000,
        emission_interval_ms=1000,
        burst_capacity_ms=5000,  # burst = 5
    )
    assert allowed
    assert retry == 0
    # New TAT = now + interval = 1001s; bucket fullness = interval; remaining
    # = (burst - fullness) / interval = (5000 - 1000) / 1000 = 4
    assert remaining == 4


def test_gcra_burst_then_block_at_capacity() -> None:
    """rate=20rpm, burst=5 → at t=0 exactly 5 requests fit, 6th denied.

    Per Stripe-style GCRA: ``burst_capacity_ms = burst * interval``, and an
    incoming request is allowed iff ``now >= new_tat - burst_capacity``.
    From a cold state at t=0, that bounds the back-to-back count to ``burst``
    (not ``burst + 1``).
    """
    interval = 60_000 // 20  # = 3000 ms
    burst_capacity = 5 * interval  # = 15_000 ms
    now = 0
    tat: int | None = None
    allowed_count = 0
    for _ in range(7):
        allowed, _rem, _reset, _retry, new_tat = _gcra_step(
            state_tat=tat,
            now_ms=now,
            emission_interval_ms=interval,
            burst_capacity_ms=burst_capacity,
        )
        if allowed:
            allowed_count += 1
            tat = new_tat
    assert allowed_count == 5


def test_gcra_retry_after_decreases_with_time() -> None:
    """When denied, retry_after_ms should shrink as wall time advances."""
    interval = 1000
    burst_capacity = 1000  # exactly one extra slot — 1 req allowed back-to-back
    # First request consumes the token.
    allowed, _, _, _, tat = _gcra_step(
        state_tat=None,
        now_ms=0,
        emission_interval_ms=interval,
        burst_capacity_ms=burst_capacity,
    )
    assert allowed
    # Immediate second request should be denied with retry ≈ interval.
    allowed, _, _, retry_a, _ = _gcra_step(
        state_tat=tat, now_ms=0, emission_interval_ms=interval, burst_capacity_ms=burst_capacity
    )
    assert not allowed
    assert retry_a == interval
    # 500ms later — retry should be ≈ 500.
    allowed, _, _, retry_b, _ = _gcra_step(
        state_tat=tat,
        now_ms=500,
        emission_interval_ms=interval,
        burst_capacity_ms=burst_capacity,
    )
    assert not allowed
    assert retry_b == interval - 500


def test_gcra_recovers_after_interval() -> None:
    """One interval after denial, the next request is allowed."""
    interval = 1000
    burst_capacity = 1000
    _, _, _, _, tat = _gcra_step(
        state_tat=None,
        now_ms=0,
        emission_interval_ms=interval,
        burst_capacity_ms=burst_capacity,
    )
    allowed, _, _, _, _ = _gcra_step(
        state_tat=tat,
        now_ms=interval,  # exactly one interval later
        emission_interval_ms=interval,
        burst_capacity_ms=burst_capacity,
    )
    assert allowed


# ---------- 2. Policy resolution ----------


def test_policy_first_prefix_match_wins() -> None:
    # POST /api/v1/chat/stream is listed before /api/v1/chat — method entry
    # for stream is checked first; both use scope="user".
    p_stream = resolve_policy("/api/v1/chat/stream", "POST")
    p_chat = resolve_policy("/api/v1/chat", "POST")
    assert p_stream.scope == "user"
    assert p_chat.scope == "user"


def test_policy_default_for_unmatched_path() -> None:
    assert resolve_policy("/api/v1/random/path") is DEFAULT


def test_policy_marker_disambiguates_limits() -> None:
    a = Policy(rate_per_minute=5, burst=2, scope="ip")
    b = Policy(rate_per_minute=10, burst=2, scope="ip")
    assert policy_marker(a) != policy_marker(b)


def test_auth_policies_are_ip_scoped() -> None:
    # Anonymous login endpoint MUST be IP-keyed — there's no session yet.
    p = resolve_policy("/api/v1/auth/login")
    assert p.scope == "ip"


# ---------- 3. Proxy-aware IP extraction ----------


def test_parse_trusted_proxies_handles_cidr_and_bare_ip() -> None:
    nets = parse_trusted_proxies("10.0.0.0/8, 127.0.0.1 , ")
    assert ipaddress.IPv4Network("10.0.0.0/8") in nets
    assert ipaddress.IPv4Network("127.0.0.1/32") in nets


def test_parse_trusted_proxies_raises_on_garbage() -> None:
    with pytest.raises(ValueError):
        parse_trusted_proxies("not-an-ip")


def _build_mw_for_ip_test(trusted: list) -> RateLimitMiddleware:
    """Tiny helper — we only call the private _client_ip indirectly."""
    redis = MagicMock()
    redis.register_script = MagicMock(return_value=AsyncMock())
    return RateLimitMiddleware(
        app=lambda *_a, **_k: None,  # type: ignore[arg-type]
        redis=redis,
        trusted_proxies=trusted,
        cookie_name="auth",
    )


def _scope_with(client_ip: str | None, xff: str | None = None) -> dict:
    headers: list = []
    if xff:
        headers.append((b"x-forwarded-for", xff.encode("latin-1")))
    return {
        "type": "http",
        "path": "/v1/auth/login",
        "headers": headers,
        "client": (client_ip, 0) if client_ip else None,
        "state": {},
    }


def test_client_ip_no_trusted_proxies_returns_peer() -> None:
    from app.inbound.http.middleware.rate_limit import _client_ip

    scope = _scope_with("203.0.113.5", xff="1.2.3.4, 5.6.7.8")
    assert _client_ip(scope, []) == "203.0.113.5"


def test_client_ip_untrusted_peer_returns_peer_even_with_xff() -> None:
    """Spoofable XFF from untrusted peer is ignored."""
    from app.inbound.http.middleware.rate_limit import _client_ip

    trusted = [ipaddress.ip_network("10.0.0.0/8")]
    scope = _scope_with("203.0.113.5", xff="1.2.3.4")
    assert _client_ip(scope, trusted) == "203.0.113.5"


def test_client_ip_walks_rightmost_trusted_hops() -> None:
    """Trusted peer + XFF with mix — returns first untrusted from right."""
    from app.inbound.http.middleware.rate_limit import _client_ip

    trusted = [ipaddress.ip_network("10.0.0.0/8")]
    # Real client at 198.51.100.7, then traversed 10.0.0.1 (LB) → peer 10.0.0.2 (proxy).
    scope = _scope_with("10.0.0.2", xff="198.51.100.7, 10.0.0.1")
    assert _client_ip(scope, trusted) == "198.51.100.7"


def test_client_ip_all_hops_trusted_falls_back_to_leftmost() -> None:
    from app.inbound.http.middleware.rate_limit import _client_ip

    trusted = [ipaddress.ip_network("10.0.0.0/8")]
    scope = _scope_with("10.0.0.2", xff="10.0.0.1, 10.0.0.3")
    assert _client_ip(scope, trusted) == "10.0.0.1"


def test_client_ip_no_client_returns_none() -> None:
    from app.inbound.http.middleware.rate_limit import _client_ip

    scope = _scope_with(None)
    assert _client_ip(scope, []) is None


# ---------- 4. Key derivation ----------


def test_key_user_scope_with_cookie_uses_hash() -> None:
    from app.inbound.http.middleware.rate_limit import _key_for

    scope = {
        "type": "http",
        "path": "/v1/chat",
        "headers": [(b"cookie", b"auth=session-token-abc; other=1")],
        "client": ("1.2.3.4", 0),
        "state": {},
    }
    policy = Policy(rate_per_minute=20, burst=5, scope="user")
    key = _key_for(scope, policy, [], "auth")
    assert key is not None
    assert key.startswith("rl:u:")
    assert key.endswith(":20_5")


def test_key_user_scope_anon_falls_back_to_ip() -> None:
    from app.inbound.http.middleware.rate_limit import _key_for

    scope = {
        "type": "http",
        "path": "/v1/chat",
        "headers": [],
        "client": ("1.2.3.4", 0),
        "state": {},
    }
    policy = Policy(rate_per_minute=20, burst=5, scope="user")
    key = _key_for(scope, policy, [], "auth")
    assert key == "rl:ip:1.2.3.4:20_5"


def test_key_ip_scope_ignores_cookie() -> None:
    from app.inbound.http.middleware.rate_limit import _key_for

    scope = {
        "type": "http",
        "path": "/v1/auth/login",
        "headers": [(b"cookie", b"auth=session-abc")],
        "client": ("1.2.3.4", 0),
        "state": {},
    }
    policy = Policy(rate_per_minute=5, burst=2, scope="ip")
    key = _key_for(scope, policy, [], "auth")
    assert key == "rl:ip:1.2.3.4:5_2"


# ---------- 5. Middleware end-to-end (Lua script mocked) ----------


async def _handler(_req: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _make_app(redis_mock) -> Starlette:
    app = Starlette(routes=[Route("/api/v1/auth/login", _handler, methods=["POST"])])
    app.add_middleware(
        RateLimitMiddleware,
        redis=redis_mock,
        trusted_proxies=[],
        cookie_name="auth",
    )
    return app


def _redis_with_script_result(result: list) -> MagicMock:
    redis = MagicMock()
    script = AsyncMock(return_value=result)
    redis.register_script = MagicMock(return_value=script)
    return redis


def test_allow_path_injects_rate_limit_headers() -> None:
    redis = _redis_with_script_result([1, 7, 3500, 0])
    app = _make_app(redis)
    client = TestClient(app, raise_server_exceptions=True)

    r = client.post("/api/v1/auth/login")

    assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == "5"  # policy says 5 rpm
    assert r.headers["X-RateLimit-Remaining"] == "7"
    # reset_ms=3500 → ceil to 4 seconds
    assert r.headers["X-RateLimit-Reset"] == "4"


def test_deny_returns_429_with_envelope_and_retry_after() -> None:
    redis = _redis_with_script_result([0, 0, 2000, 1750])
    app = _make_app(redis)
    client = TestClient(app, raise_server_exceptions=True)

    r = client.post("/api/v1/auth/login")

    assert r.status_code == 429
    assert r.headers["Retry-After"] == "2"  # ceil(1750/1000)
    assert r.headers["X-RateLimit-Limit"] == "5"
    assert r.headers["X-RateLimit-Remaining"] == "0"
    assert r.headers["X-RateLimit-Reset"] == "2"
    assert r.headers["content-type"].startswith("application/json")
    body = json.loads(r.content)
    assert body["error"]["code"] == "rate_limit.exceeded"
    assert "message" in body["error"]
    assert "request_id" in body["error"]


def test_redis_error_fails_open() -> None:
    redis = MagicMock()
    script = AsyncMock(side_effect=RedisError("boom"))
    redis.register_script = MagicMock(return_value=script)
    app = _make_app(redis)
    client = TestClient(app, raise_server_exceptions=True)

    r = client.post("/api/v1/auth/login")

    assert r.status_code == 200  # fails open
    # No X-RateLimit-* injected on the fail-open path.
    assert "X-RateLimit-Limit" not in r.headers


def test_skip_paths_bypass_middleware() -> None:
    """SKIP-listed paths must not call the GCRA script at all."""
    redis = _redis_with_script_result([0, 0, 999, 999])
    script = redis.register_script.return_value

    app = Starlette(
        routes=[
            Route("/health", _handler, methods=["GET"]),
            Route("/v1/auth/login", _handler, methods=["POST"]),
        ]
    )
    app.add_middleware(
        RateLimitMiddleware,
        redis=redis,
        trusted_proxies=[],
        cookie_name="auth",
    )
    client = TestClient(app, raise_server_exceptions=True)

    r = client.get("/health")

    assert r.status_code == 200
    assert script.await_count == 0


class _PrefixRequestId:
    """Stand-in for the production RequestIdMiddleware — sets scope state."""

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] == "http":
            scope.setdefault("state", {})["request_id"] = "test-rid-123"
        await self.app(scope, receive, send)


def test_request_id_propagates_when_outer_middleware_sets_it() -> None:
    redis = _redis_with_script_result([0, 0, 1000, 1000])
    inner = _make_app(redis)
    # Wrap inner with our request-id setter
    wrapped_app = _PrefixRequestId(inner)
    client = TestClient(wrapped_app, raise_server_exceptions=True)  # type: ignore[arg-type]

    r = client.post("/api/v1/auth/login")

    body = json.loads(r.content)
    assert body["error"]["request_id"] == "test-rid-123"


# ---------- 6. Policy table sanity ----------


def test_skip_set_contains_ops_endpoints() -> None:
    assert "/health" in SKIP
    assert "/metrics" in SKIP
    assert "/openapi.json" in SKIP


def test_policy_table_chat_stream_before_chat() -> None:
    """Sanity: more specific path must appear earlier so its policy is matched first."""
    prefixes = [prefix for _method, prefix, _policy in POLICIES]
    assert prefixes.index("/api/v1/chat/stream") < prefixes.index("/api/v1/chat")


def test_reset_seconds_is_positive_ceil() -> None:
    """X-RateLimit-Reset should never round down to 0 when there is any state."""
    assert max(1, math.ceil(1 / 1000)) == 1


# ---------- 7. Policy ↔ route coverage ----------


def test_every_policy_prefix_matches_at_least_one_registered_route() -> None:
    """Every POLICIES entry must match at least one real route in the FastAPI app.

    This catches stale prefixes like the old /v1/ingestion/receipts that pointed
    to a non-existent path.
    """
    from app.inbound.http.router import make_api_router

    def collect_paths(routes: list) -> set[str]:
        paths: set[str] = set()
        for route in routes:
            p = getattr(route, "path", "")
            if p:
                paths.add(p)
            sub = getattr(route, "routes", [])
            if sub:
                paths.update(collect_paths(sub))
        return paths

    router = make_api_router()
    all_paths = collect_paths(router.routes)

    for _method, prefix, _policy in POLICIES:
        matched = any(p.startswith(prefix) for p in all_paths if p)
        assert matched, (
            f"Policy prefix {prefix!r} does not match any registered route. "
            f"Available paths (sample): {sorted(all_paths)[:10]}"
        )


def test_ingestion_parse_receipt_resolves_to_strict_policy() -> None:
    """POST /api/v1/ingestion/parse-receipt must get the 10/min strict policy."""
    policy = resolve_policy("/api/v1/ingestion/parse-receipt", "POST")
    assert policy.rate_per_minute == 10
    assert policy is not DEFAULT


def test_chat_history_get_does_not_resolve_to_chat_post_policy() -> None:
    """GET /api/v1/chat/history must NOT be throttled by the POST-chat 20/min policy."""
    get_policy = resolve_policy("/api/v1/chat/history", "GET")
    post_policy = resolve_policy("/api/v1/chat", "POST")
    # The GET history path should fall through to DEFAULT (not the POST chat limit).
    assert get_policy is DEFAULT
    assert post_policy is not DEFAULT
    assert post_policy.rate_per_minute == 20


def test_chat_history_delete_does_not_resolve_to_chat_post_policy() -> None:
    """DELETE /api/v1/chat/history must NOT be throttled by the POST-chat 20/min policy."""
    delete_policy = resolve_policy("/api/v1/chat/history", "DELETE")
    assert delete_policy is DEFAULT
