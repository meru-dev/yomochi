from dataclasses import dataclass

from app.application.insights.ports.insight_repository import InsightRepository
from app.domain.entities.insight import Insight
from app.domain.value_objects.ids import InsightId, UserId


class InsightNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GetInsightQuery:
    insight_id: InsightId
    user_id: UserId


class GetInsightUseCase:
    def __init__(self, insight_repo: InsightRepository) -> None:
        self._repo = insight_repo

    async def __call__(self, query: GetInsightQuery) -> Insight:
        insight = await self._repo.get_by_id(query.insight_id, query.user_id)
        if insight is None:
            raise InsightNotFoundError(str(query.insight_id))
        return insight
