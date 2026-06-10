import asyncio
from concurrent.futures import ThreadPoolExecutor

import bcrypt

from app.domain.value_objects.password import RawPassword, UserPasswordHash


class BcryptPasswordHasher:
    def __init__(self, thread_pool: ThreadPoolExecutor) -> None:
        self._pool = thread_pool

    async def hash(self, password: RawPassword) -> UserPasswordHash:
        loop = asyncio.get_running_loop()
        raw = password.value.encode()
        hashed: bytes = await loop.run_in_executor(
            self._pool,
            lambda: bcrypt.hashpw(raw, bcrypt.gensalt()),
        )
        return UserPasswordHash(hashed.decode())

    async def verify(self, password: RawPassword, hash_: UserPasswordHash) -> bool:
        loop = asyncio.get_running_loop()
        raw = password.value.encode()
        stored = hash_.value.encode()
        result: bool = await loop.run_in_executor(
            self._pool,
            lambda: bcrypt.checkpw(raw, stored),
        )
        return result
