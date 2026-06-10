from abc import abstractmethod
from typing import Protocol

from app.application.common.outbox_event import OutboxEvent


class OutboxRepository(Protocol):
    @abstractmethod
    async def append(self, event: OutboxEvent) -> None: ...
