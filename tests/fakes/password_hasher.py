from app.domain.value_objects.password import RawPassword, UserPasswordHash

_PREFIX = "plain:"


class PlaintextHasher:
    """Fast in-memory password hasher for tests. Never use in production."""

    async def hash(self, password: RawPassword) -> UserPasswordHash:
        return UserPasswordHash(f"{_PREFIX}{password.value}")

    async def verify(self, password: RawPassword, hash_: UserPasswordHash) -> bool:
        return hash_.value == f"{_PREFIX}{password.value}"


class SpyHasher:
    """Wraps PlaintextHasher and counts verify() calls."""

    def __init__(self) -> None:
        self._inner = PlaintextHasher()
        self.verify_call_count = 0

    async def hash(self, password: RawPassword) -> UserPasswordHash:
        return await self._inner.hash(password)

    async def verify(self, password: RawPassword, hash_: UserPasswordHash) -> bool:
        self.verify_call_count += 1
        return await self._inner.verify(password, hash_)
