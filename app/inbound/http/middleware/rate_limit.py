from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import time
from typing import TYPE_CHECKING

from redis.exceptions import RedisError
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.inbound.http.middleware.rate_limit_policy import (
    SKIP,
    Policy,
    policy_marker,
    resolve_policy,
)
from app.outbound.observability.prometheus import rate_limit_redis_error_total

if TYPE_CHECKING:
    from redis.asyncio import Redis

# GCRA Lua script — single RTT, atomic state mutation.
#
# KEYS[1] = rate-limit key (str)
# ARGV[1] = now_ms (int)
# ARGV[2] = emission_interval_ms = floor(60_000 / rate_per_minute)
# ARGV[3] = burst_capacity_ms     = burst * emission_interval_ms
#
# Returns: {allowed (0|1), remaining (int), reset_ms (int from now), retry_after_ms (int)}
#
# TTL bound: we keep the key alive for ``burst_capacity + emission_interval``
# past TAT — that's the maximum time during which the key has any throttling
# effect. After that, returning to "no state" is identical to a fresh client.
_GCRA_LUA = """
local tat = tonumber(redis.call('GET', KEYS[1]) or ARGV[1])
local now = tonumber(ARGV[1])
local interval = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])
if tat < now then tat = now end
local new_tat = tat + interval
local allow_at = new_tat - burst
if now >= allow_at then
  local ttl = burst + interval
  redis.call('SET', KEYS[1], new_tat, 'PX', ttl)
  local remaining = math.floor((burst - (new_tat - now)) / interval)
  if remaining < 0 then remaining = 0 end
  return {1, remaining, new_tat - now, 0}
else
  local retry_after_ms = allow_at - now
  return {0, 0, tat - now, retry_after_ms}
end
"""


class RateLimitMiddleware:
    """Pure ASGI middleware enforcing per-endpoint GCRA limits.

    - Per-user key (session cookie hash) when authenticated, per-IP fallback
      for anonymous traffic (or ``scope="ip"`` policies).
    - Proxy-aware client IP: rightmost trusted hop walk over ``X-Forwarded-For``
      (RFC 7239 §7.5) — defaulting to ``scope["client"]`` when no proxies are
      trusted.
    - Standard ``X-RateLimit-{Limit,Remaining,Reset}`` headers on success,
      ``Retry-After`` on 429.
    - Fail-open on ``RedisError`` (and increments
      ``rate_limit_redis_error_total``).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        redis: Redis,  # type: ignore[type-arg]
        trusted_proxies: list[ipaddress.IPv4Network | ipaddress.IPv6Network] | None = None,
        cookie_name: str = "auth",
    ) -> None:
        self.app = app
        self._redis = redis
        self._trusted_proxies = trusted_proxies or []
        self._cookie_name = cookie_name
        self._gcra = redis.register_script(_GCRA_LUA)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in SKIP:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        policy = resolve_policy(path)
        key = _key_for(scope, policy, self._trusted_proxies, self._cookie_name)
        if key is None:
            # No client and no cookie — we cannot identify the caller. Deny.
            await _send_429(
                send,
                request_id=_request_id(scope),
                policy=policy,
                retry_after_ms=60_000,
                reset_ms=60_000,
            )
            return

        emission_interval_ms = 60_000 // max(policy.rate_per_minute, 1)
        burst_capacity_ms = policy.burst * emission_interval_ms
        now_ms = int(time.time() * 1000)

        try:
            result = await self._gcra(
                keys=[key],
                args=[now_ms, emission_interval_ms, burst_capacity_ms],
            )
        except RedisError:
            # Fail-open: a Redis outage must not take down the API.
            rate_limit_redis_error_total.inc()
            await self.app(scope, receive, send)
            return

        allowed = int(result[0]) == 1
        remaining = int(result[1])
        reset_ms = int(result[2])
        retry_after_ms = int(result[3])

        if not allowed:
            await _send_429(
                send,
                request_id=_request_id(scope),
                policy=policy,
                retry_after_ms=retry_after_ms,
                reset_ms=reset_ms,
            )
            return

        reset_seconds = max(1, math.ceil(reset_ms / 1000))
        limit_str = str(policy.rate_per_minute).encode("ascii")
        remaining_str = str(remaining).encode("ascii")
        reset_str = str(reset_seconds).encode("ascii")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = limit_str.decode("ascii")
                headers["X-RateLimit-Remaining"] = remaining_str.decode("ascii")
                headers["X-RateLimit-Reset"] = reset_str.decode("ascii")
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ---------- internals ----------


def _request_id(scope: Scope) -> str | None:
    state = scope.get("state")
    if isinstance(state, dict):
        rid = state.get("request_id")
        if isinstance(rid, str):
            return rid
    return None


def _read_cookie(scope: Scope, cookie_name: str) -> str | None:
    for name, value in scope.get("headers", ()):
        if name != b"cookie":
            continue
        try:
            decoded = value.decode("latin-1")
        except UnicodeDecodeError:
            return None
        for pair in decoded.split(";"):
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            if k.strip() == cookie_name:
                return str(v.strip())
    return None


def _is_trusted(
    ip_str: str,
    trusted: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in trusted)


def _client_ip(
    scope: Scope,
    trusted: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> str | None:
    """RFC 7239 §7.5 rightmost-trusted-hop walk.

    1. If no trusted proxies configured, return the peer IP as-is.
    2. If the peer is not trusted, return the peer IP (don't honor XFF
       from an untrusted source — spoofable).
    3. Otherwise walk XFF right-to-left, skipping trusted hops, and return
       the first untrusted address. If every hop is trusted, fall back to
       the leftmost.
    """
    client = scope.get("client")
    peer_ip: str | None = str(client[0]) if client else None
    if not peer_ip:
        return None
    if not trusted:
        return peer_ip
    if not _is_trusted(peer_ip, trusted):
        return peer_ip
    xff_header: bytes | None = None
    for name, value in scope.get("headers", ()):
        if name == b"x-forwarded-for":
            xff_header = value
            break
    if not xff_header:
        return peer_ip
    try:
        decoded = xff_header.decode("latin-1")
    except UnicodeDecodeError:
        return peer_ip
    parts = [p.strip() for p in decoded.split(",") if p.strip()]
    if not parts:
        return peer_ip
    for candidate in reversed(parts):
        if not _is_trusted(candidate, trusted):
            return candidate
    return parts[0]


def _key_for(
    scope: Scope,
    policy: Policy,
    trusted: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
    cookie_name: str,
) -> str | None:
    marker = policy_marker(policy)
    if policy.scope == "user":
        cookie_val = _read_cookie(scope, cookie_name)
        if cookie_val:
            h = hashlib.sha256(cookie_val.encode()).hexdigest()[:32]
            return f"rl:u:{h}:{marker}"
        # fall through to IP keying for anonymous callers
    ip = _client_ip(scope, trusted)
    if not ip:
        return None
    return f"rl:ip:{ip}:{marker}"


def _error_body(message: str, request_id: str | None) -> bytes:
    return json.dumps(
        {
            "error": {
                "code": "rate_limit.exceeded",
                "message": message,
                "request_id": request_id,
            }
        }
    ).encode("utf-8")


async def _send_429(
    send: Send,
    *,
    request_id: str | None,
    policy: Policy,
    retry_after_ms: int,
    reset_ms: int,
) -> None:
    body = _error_body("Rate limit exceeded", request_id)
    retry_after_s = max(1, math.ceil(retry_after_ms / 1000))
    reset_s = max(1, math.ceil(reset_ms / 1000))
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"retry-after", str(retry_after_s).encode("ascii")),
        (b"x-ratelimit-limit", str(policy.rate_per_minute).encode("ascii")),
        (b"x-ratelimit-remaining", b"0"),
        (b"x-ratelimit-reset", str(reset_s).encode("ascii")),
    ]
    await send({"type": "http.response.start", "status": 429, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


def parse_trusted_proxies(
    raw: str,
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse a comma-separated list of CIDRs/IPs into network objects.

    Bare IPs become /32 (or /128 for IPv6). Empty entries are skipped.
    Malformed entries raise ``ValueError`` so misconfiguration fails fast at
    startup rather than silently disabling proxy trust.
    """
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        nets.append(ipaddress.ip_network(token, strict=False))
    return nets
