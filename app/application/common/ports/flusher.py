from abc import abstractmethod
from typing import Protocol


class Flusher(Protocol):
    @abstractmethod
    async def flush(self) -> None: ...
