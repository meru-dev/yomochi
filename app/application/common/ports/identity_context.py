from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.ids import SessionId, UserId


class IdentityContext(Protocol):
    @property
    @abstractmethod
    def user_id(self) -> UserId: ...

    @property
    @abstractmethod
    def session_id(self) -> SessionId: ...
