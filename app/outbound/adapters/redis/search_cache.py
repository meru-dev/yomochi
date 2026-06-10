import hashlib
import json
from uuid import UUID

from redis.asyncio import Redis

from app.domain.value_objects.ids import UserId
from app.outbound.observability.prometheus import (
    search_cache_hits_total,
    search_cache_misses_total,
)

_SEARCH_CACHE_KEY = "search_cache:{uid}:{query_hash}"


class RedisSearchCache:
    def __init__(self, redis: Redis, ttl: int) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._ttl = ttl

    async def get(self, user_id: UserId, query: str) -> list[UUID] | None:
        uid = str(user_id.value)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        key = _SEARCH_CACHE_KEY.format(uid=uid, query_hash=query_hash)

        raw = await self._redis.get(key)
        if raw is None:
            search_cache_misses_total.inc()
            return None

        data = json.loads(raw)
        search_cache_hits_total.inc()
        return [UUID(s) for s in data]

    async def set(self, user_id: UserId, query: str, transaction_ids: list[UUID]) -> None:
        uid = str(user_id.value)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        key = _SEARCH_CACHE_KEY.format(uid=uid, query_hash=query_hash)

        data = json.dumps([str(tx_id) for tx_id in transaction_ids])
        await self._redis.set(key, data, ex=self._ttl)
