from abc import abstractmethod
from typing import Protocol

from app.application.users.password_reset_token import PasswordResetToken
from app.domain.value_objects.ids import PasswordResetTokenId


class PasswordResetTokenStore(Protocol):
    @abstractmethod
    async def save(self, token: PasswordResetToken) -> None: ...

    @abstractmethod
    async def get_valid(self, token_hash: str) -> PasswordResetToken | None: ...

    @abstractmethod
    async def invalidate(self, token_id: PasswordResetTokenId) -> None: ...
