from abc import abstractmethod
from typing import Protocol

from app.application.common.audit_event import AuditEvent


class AuditLog(Protocol):
    @abstractmethod
    async def record(self, event: AuditEvent) -> None: ...
