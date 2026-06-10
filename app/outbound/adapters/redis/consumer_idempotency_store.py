from redis.asyncio import Redis


class RedisConsumerIdempotencyStore:
    def __init__(self, redis: Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis

    async def is_processed(self, event_id: str) -> bool:
        return bool(await self._redis.exists(f"consumer:idempotency:{event_id}"))

    async def mark_processed(self, event_id: str, ttl_seconds: int) -> None:
        await self._redis.set(f"consumer:idempotency:{event_id}", "1", ex=ttl_seconds)

    async def increment_failures(self, event_id: str) -> int:
        key = f"consumer:failures:{event_id}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 86400)
        return int(count)
