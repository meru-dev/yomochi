from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.ids import SessionId, UserId


class TokenDecoder(Protocol):
    @abstractmethod
    def decode(self, token: str) -> tuple[UserId, SessionId] | None: ...
