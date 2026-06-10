from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from app.domain.value_objects.email import Email


class Mailer(Protocol):
    @abstractmethod
    async def send_password_reset(self, to: Email, token: str, expires_at: datetime) -> None: ...
