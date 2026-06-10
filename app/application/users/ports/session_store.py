from abc import abstractmethod
from collections.abc import Sequence
from typing import Protocol

from app.application.users.session import Session
from app.domain.value_objects.ids import SessionId, UserId


class SessionStore(Protocol):
    @abstractmethod
    async def save(self, session: Session) -> None: ...

    @abstractmethod
    async def get(self, session_id: SessionId, user_id: UserId) -> Session | None: ...

    @abstractmethod
    async def revoke(self, session_id: SessionId, user_id: UserId) -> None: ...

    @abstractmethod
    async def list_active(self, user_id: UserId) -> Sequence[Session]: ...

    @abstractmethod
    async def revoke_all(self, user_id: UserId) -> None: ...
