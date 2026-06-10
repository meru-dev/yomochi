from app.domain.value_objects.password import RawPassword, UserPasswordHash

_PREFIX = "plain:"


class PlaintextHasher:
    """Fast in-memory password hasher for tests. Never use in production."""

    async def hash(self, password: RawPassword) -> UserPasswordHash:
        return UserPasswordHash(f"{_PREFIX}{password.value}")

    async def verify(self, password: RawPassword, hash_: UserPasswordHash) -> bool:
        return hash_.value == f"{_PREFIX}{password.value}"
