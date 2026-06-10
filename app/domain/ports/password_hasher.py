from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.password import RawPassword, UserPasswordHash


class PasswordHasher(Protocol):
    @abstractmethod
    async def hash(self, password: RawPassword) -> UserPasswordHash: ...

    @abstractmethod
    async def verify(self, password: RawPassword, hash_: UserPasswordHash) -> bool: ...
