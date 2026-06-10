from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.value_objects.ids import UserId


@dataclass(frozen=True)
class ChunkToWrite:
    user_id: UserId
    chunk_type: str  # "monthly_summary" | "behavioral_shift"
    period_year: int
    period_month: int
    content: str
    embedding: list[float]
    semantic_hash: str
    metadata: dict[str, Any]


class ChunkWriter(Protocol):
    @abstractmethod
    async def upsert(self, chunk: ChunkToWrite) -> None: ...

    @abstractmethod
    async def delete_for_period(self, user_id: UserId, year: int, month: int) -> None: ...
