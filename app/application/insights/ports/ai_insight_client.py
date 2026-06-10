from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol

from app.application.insights.ports.chunk_retriever import RetrievedChunk
from app.domain.value_objects.enums import Period


@dataclass(frozen=True)
class InsightRequest:
    period: Period
    period_year: int
    period_month: int
    chunks: list[RetrievedChunk]
    user_question: str | None = None


@dataclass(frozen=True)
class InsightResponse:
    title: str
    description: str
    impact_score: int  # 1-10
    prompt_tokens: int
    completion_tokens: int


class AIInsightClient(Protocol):
    @abstractmethod
    async def generate(self, request: InsightRequest) -> InsightResponse: ...
