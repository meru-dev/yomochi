from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.ids import UserId


class DirtyPeriodMarker(Protocol):
    """Consumer-owned port — transactions tells \"this (user, year, month) needs
    re-embedding\" without depending on insights internals.

    The single adapter delegates to SqlaDirtyPeriodRepository.mark_dirty.
    """

    @abstractmethod
    async def mark_dirty(self, user_id: UserId, year: int, month: int) -> None: ...
