from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.common.cursor import decode_cursor, encode_cursor
from app.application.insights.ports.insight_repository import InsightRepository
from app.domain.entities.insight import Insight
from app.domain.value_objects.enums import Period
from app.domain.value_objects.ids import InsightId, UserId


@dataclass(frozen=True, slots=True)
class ListInsightsQuery:
    user_id: UserId
    limit: int = 20
    cursor: str | None = None
    period: Period | None = None
    period_year: int | None = None
    period_month: int | None = None


@dataclass(frozen=True, slots=True)
class ListInsightsResult:
    insights: tuple[Insight, ...]
    next_cursor: str | None


def _encode_cursor(insight: Insight) -> str:
    return encode_cursor({"created_at": insight.created_at.isoformat(), "id": str(insight.id_)})


def _decode_cursor(cursor: str) -> tuple[datetime, InsightId]:
    raw = decode_cursor(cursor)
    return datetime.fromisoformat(raw["created_at"]), InsightId(UUID(raw["id"]))


class ListInsightsUseCase:
    def __init__(self, insight_repo: InsightRepository) -> None:
        self._repo = insight_repo

    async def __call__(self, query: ListInsightsQuery) -> ListInsightsResult:
        cursor_tuple = _decode_cursor(query.cursor) if query.cursor else None
        insights = await self._repo.list_by_user(
            user_id=query.user_id,
            limit=query.limit,
            cursor=cursor_tuple,
            period=query.period,
            period_year=query.period_year,
            period_month=query.period_month,
        )
        next_cursor = _encode_cursor(insights[-1]) if len(insights) == query.limit else None
        return ListInsightsResult(insights=tuple(insights), next_cursor=next_cursor)
