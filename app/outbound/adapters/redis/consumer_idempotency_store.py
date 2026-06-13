from redis.asyncio import Redis

_INCR_WITH_TTL_LUA = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return c
"""

_FAILURE_TTL = 86400


class RedisConsumerIdempotencyStore:
    def __init__(self, redis: Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._incr_with_ttl = redis.register_script(_INCR_WITH_TTL_LUA)

    async def is_processed(self, event_id: str) -> bool:
        return bool(await self._redis.exists(f"consumer:idempotency:{event_id}"))

    async def mark_processed(self, event_id: str, ttl_seconds: int) -> None:
        await self._redis.set(f"consumer:idempotency:{event_id}", "1", ex=ttl_seconds)

    async def increment_failures(self, event_id: str) -> int:
        key = f"consumer:failures:{event_id}"
        count = await self._incr_with_ttl(keys=[key], args=[_FAILURE_TTL])
        return int(count)
