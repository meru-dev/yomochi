from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.value_objects.ids import UserId


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    chunk_type: str  # "monthly_summary" | "behavioral_shift" | "user_portrait"
    period_label: str
    metadata: dict[str, Any]


class ChunkRetriever(Protocol):
    @abstractmethod
    async def search(
        self,
        user_id: UserId,
        query_embedding: list[float],
        monthly_top_k: int = 3,
        shift_top_k: int = 2,
    ) -> list[RetrievedChunk]: ...

    @abstractmethod
    async def get_portrait(self, user_id: UserId) -> RetrievedChunk | None: ...
