from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Query, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.insights.use_cases.list_insights import ListInsightsQuery, ListInsightsUseCase
from app.domain.value_objects.enums import Period
from app.inbound.http.controllers.insights.get import InsightResponse, _serialize

router = ErrorAwareRouter()


class InsightListResponse(BaseModel):
    items: list[InsightResponse]
    next_cursor: str | None
    has_more: bool


@router.get("", status_code=status.HTTP_200_OK, response_model=InsightListResponse)
@inject
async def list_insights(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ListInsightsUseCase],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    period: Period | None = Query(default=None),  # noqa: B008
    period_year: int | None = Query(default=None, ge=2000, le=2100),
    period_month: int | None = Query(default=None, ge=1, le=12),
) -> InsightListResponse:
    result = await use_case(
        ListInsightsQuery(
            user_id=identity.user_id,
            limit=limit,
            cursor=cursor,
            period=period,
            period_year=period_year,
            period_month=period_month,
        )
    )
    return InsightListResponse(
        items=[_serialize(i) for i in result.insights],
        next_cursor=result.next_cursor,
        has_more=result.next_cursor is not None,
    )
