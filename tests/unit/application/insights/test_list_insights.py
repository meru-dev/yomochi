from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import uuid_utils as uuid

from app.application.insights.use_cases.list_insights import (
    ListInsightsQuery,
    ListInsightsResult,
    ListInsightsUseCase,
)
from app.domain.value_objects.ids import UserId


@pytest.mark.asyncio
async def test_list_insights_returns_cursor_when_full_page():
    user_id = UserId(uuid.uuid7())
    from app.domain.entities.insight import Insight
    from app.domain.value_objects.enums import InsightStatus, Period
    from app.domain.value_objects.ids import InsightId

    def make_insight(created_at: datetime) -> Insight:
        return Insight(
            id_=InsightId(uuid.uuid7()),
            user_id=user_id,
            period=Period.MONTHLY,
            period_year=2025,
            period_month=1,
            status=InsightStatus.COMPLETED,
            context_quality=None,
            title="T",
            description="D",
            impact_score=5,
            generated_at=created_at,
            error_message=None,
            created_at=created_at,
        )

    insights = [make_insight(datetime(2025, 1, i + 1, tzinfo=UTC)) for i in range(3)]

    repo = AsyncMock()
    repo.list_by_user = AsyncMock(return_value=insights)

    use_case = ListInsightsUseCase(insight_repo=repo)
    result = await use_case(ListInsightsQuery(user_id=user_id, limit=3, cursor=None))

    assert isinstance(result, ListInsightsResult)
    assert len(result.insights) == 3
    assert result.next_cursor is not None


@pytest.mark.asyncio
async def test_list_insights_passes_period_filters_to_repo():
    user_id = UserId(uuid.uuid7())
    from app.domain.value_objects.enums import Period

    repo = AsyncMock()
    repo.list_by_user = AsyncMock(return_value=[])

    use_case = ListInsightsUseCase(insight_repo=repo)
    await use_case(
        ListInsightsQuery(
            user_id=user_id,
            limit=10,
            cursor=None,
            period=Period.MONTHLY,
            period_year=2026,
            period_month=6,
        )
    )

    repo.list_by_user.assert_awaited_once()
    kwargs = repo.list_by_user.call_args.kwargs
    assert kwargs["period"] == Period.MONTHLY
    assert kwargs["period_year"] == 2026
    assert kwargs["period_month"] == 6


@pytest.mark.asyncio
async def test_list_insights_period_filters_default_to_none():
    user_id = UserId(uuid.uuid7())

    repo = AsyncMock()
    repo.list_by_user = AsyncMock(return_value=[])

    use_case = ListInsightsUseCase(insight_repo=repo)
    await use_case(ListInsightsQuery(user_id=user_id, limit=10))

    kwargs = repo.list_by_user.call_args.kwargs
    assert kwargs["period"] is None
    assert kwargs["period_year"] is None
    assert kwargs["period_month"] is None


@pytest.mark.asyncio
async def test_list_insights_no_cursor_on_partial_page():
    user_id = UserId(uuid.uuid7())
    from app.domain.entities.insight import Insight
    from app.domain.value_objects.enums import InsightStatus, Period
    from app.domain.value_objects.ids import InsightId

    insights = [
        Insight(
            id_=InsightId(uuid.uuid7()),
            user_id=user_id,
            period=Period.MONTHLY,
            period_year=2025,
            period_month=1,
            status=InsightStatus.COMPLETED,
            context_quality=None,
            title="T",
            description="D",
            impact_score=5,
            generated_at=datetime(2025, 1, 1, tzinfo=UTC),
            error_message=None,
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
    ]

    repo = AsyncMock()
    repo.list_by_user = AsyncMock(return_value=insights)

    use_case = ListInsightsUseCase(insight_repo=repo)
    result = await use_case(ListInsightsQuery(user_id=user_id, limit=20, cursor=None))

    assert result.next_cursor is None
