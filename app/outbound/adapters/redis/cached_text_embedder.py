import hashlib
import json

from redis.asyncio import Redis

from app.application.common.ports.text_embedder import TextEmbedder

_TTL_SECONDS = 86400  # 24h
_PREFIX = "embed:"


def _cache_key(text: str) -> str:
    """Full 256-bit hex digest — no birthday collisions at realistic cache sizes."""
    return _PREFIX + hashlib.sha256(text.encode()).hexdigest()


class CachedTextEmbedder:
    """Decorator that caches TextEmbedder results in Redis."""

    def __init__(self, inner: TextEmbedder, redis: Redis) -> None:  # type: ignore[type-arg]
        self._inner = inner
        self._redis = redis

    async def embed(self, text: str) -> list[float]:
        key = _cache_key(text)
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
            key = _cache_key(text)
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
                await self._redis.set(_cache_key(text), json.dumps(emb), ex=_TTL_SECONDS)

        return results  # type: ignore[return-value]
