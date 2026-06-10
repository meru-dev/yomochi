from typing import Literal

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.insights.use_cases.request_insight import (
    RequestInsightCommand,
    RequestInsightUseCase,
)
from app.domain.value_objects.enums import Period

router = ErrorAwareRouter()


class RequestInsightBody(BaseModel):
    period: Literal["weekly", "monthly"]
    period_year: int
    period_month: int


class RequestInsightResponse(BaseModel):
    id: str


@router.post(
    "/requests",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RequestInsightResponse,
)
@inject
async def request_insight(
    body: RequestInsightBody,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[RequestInsightUseCase],
) -> RequestInsightResponse:
    result = await use_case(
        RequestInsightCommand(
            user_id=identity.user_id,
            period=Period(body.period),
            period_year=body.period_year,
            period_month=body.period_month,
        )
    )
    return RequestInsightResponse(id=result.insight_id)
