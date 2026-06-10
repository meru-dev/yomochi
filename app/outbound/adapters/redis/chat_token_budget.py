from datetime import UTC, datetime

from redis.asyncio import Redis

from app.application.chat.ports.chat_token_budget import (
    ChatTokenBudgetExceededError,
)
from app.domain.value_objects.ids import UserId

_TTL_SECONDS = 25 * 3600


class RedisChatTokenBudget:
    def __init__(self, redis: Redis, daily_token_limit: int) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._limit = daily_token_limit

    @staticmethod
    def _key(user_id: UserId) -> str:
        today = datetime.now(UTC).date().isoformat()
        return f"tokens:chat:{user_id}:{today}"

    async def check(self, user_id: UserId) -> None:
        raw = await self._redis.get(self._key(user_id))
        current = int(raw) if raw else 0
        if current >= self._limit:
            raise ChatTokenBudgetExceededError(current=current, limit=self._limit)

    async def record(self, user_id: UserId, tokens: int) -> None:
        if tokens <= 0:
            return
        key = self._key(user_id)
        pipe = self._redis.pipeline()
        pipe.incrby(key, tokens)
        pipe.expire(key, _TTL_SECONDS)
        await pipe.execute()
