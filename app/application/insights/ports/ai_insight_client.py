from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol

from app.application.insights.ports.insight_context import InsightContextChunk
from app.domain.value_objects.enums import Period


@dataclass(frozen=True)
class InsightRequest:
    period: Period
    period_year: int
    period_month: int
    chunks: list[InsightContextChunk]
    user_question: str | None = None
    # Stable per-user key the AI adapter MAY use for provider-side cache routing
    # provider-neutral; the OpenAI adapter maps it to prompt_cache_key.
    # None = no routing hint.
    cache_key: str | None = None


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
