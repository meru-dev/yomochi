import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.insights.use_cases.get_insight import (
    GetInsightQuery,
    GetInsightUseCase,
    InsightNotFoundError,
)
from app.domain.entities.insight import Insight
from app.domain.value_objects.enums import InsightStatus, Period
from app.domain.value_objects.ids import InsightId, UserId

pytestmark = pytest.mark.asyncio


def _make_insight(user_id: UserId, insight_id: InsightId) -> Insight:
    return Insight(
        id_=insight_id,
        user_id=user_id,
        period=Period.MONTHLY,
        period_year=2026,
        period_month=4,
        status=InsightStatus.COMPLETED,
        context_quality=None,
        title="Test",
        description="Desc",
        impact_score=7,
        generated_at=datetime(2026, 4, 1, tzinfo=UTC),
        error_message=None,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )


async def test_returns_insight_when_found() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _make_insight(user_id, insight_id)

    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=insight)

    result = await GetInsightUseCase(insight_repo=repo)(
        GetInsightQuery(insight_id=insight_id, user_id=user_id)
    )

    assert result is insight
    repo.get_by_id.assert_called_once_with(insight_id, user_id)


async def test_raises_not_found_when_repo_returns_none() -> None:
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(InsightNotFoundError):
        await GetInsightUseCase(insight_repo=repo)(
            GetInsightQuery(insight_id=InsightId(uuid.uuid4()), user_id=UserId(uuid.uuid4()))
        )
