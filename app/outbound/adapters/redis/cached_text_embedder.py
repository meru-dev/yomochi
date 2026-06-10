import hashlib
import json

from redis.asyncio import Redis

from app.application.common.ports.text_embedder import TextEmbedder

_TTL_SECONDS = 86400  # 24h
_PREFIX = "embed:"


class CachedTextEmbedder:
    """Decorator that caches TextEmbedder results in Redis."""

    def __init__(self, inner: TextEmbedder, redis: Redis) -> None:  # type: ignore[type-arg]
        self._inner = inner
        self._redis = redis

    async def embed(self, text: str) -> list[float]:
        key = _PREFIX + hashlib.sha256(text.encode()).hexdigest()[:16]
        cached = await self._redis.get(key)
        if cached is not None:
            return list(json.loads(cached))
        result = await self._inner.embed(text)
        await self._redis.set(key, json.dumps(result), ex=_TTL_SECONDS)
        return result

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        misses: list[tuple[int, str]] = []

        for i, text in enumerate(texts):
            key = _PREFIX + hashlib.sha256(text.encode()).hexdigest()[:16]
            cached = await self._redis.get(key)
            if cached is not None:
                results[i] = json.loads(cached)
            else:
                misses.append((i, text))

        if misses:
            miss_texts = [t for _, t in misses]
            embeddings = await self._inner.embed_batch(miss_texts)
            for (idx, text), emb in zip(misses, embeddings, strict=False):
                results[idx] = emb
                key = _PREFIX + hashlib.sha256(text.encode()).hexdigest()[:16]
                await self._redis.set(key, json.dumps(emb), ex=_TTL_SECONDS)

        return results  # type: ignore[return-value]
