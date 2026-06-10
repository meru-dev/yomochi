from abc import abstractmethod
from typing import Protocol

from app.application.users.session import Session


class TokenEncoder(Protocol):
    @abstractmethod
    def encode(self, session: Session) -> str: ...
