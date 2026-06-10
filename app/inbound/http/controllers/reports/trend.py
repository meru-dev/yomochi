from typing import Literal

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Query, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.transactions.use_cases.get_spend_trend import (
    GetSpendTrendCommand,
    GetSpendTrendUseCase,
)

router = ErrorAwareRouter()


class TrendPoint(BaseModel):
    month: str  # "YYYY-MM" for month granularity, "YYYY-Www" (ISO year-week) for week
    total: str


class TrendResponse(BaseModel):
    points: list[TrendPoint]


@router.get("/trend", status_code=status.HTTP_200_OK, response_model=TrendResponse)
@inject
async def get_trend(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[GetSpendTrendUseCase],
    currency: str = Query(),
    months: int = Query(default=6, ge=1, le=52, description="Bucket count (months or weeks)"),
    tx_type: str = Query(default="expense", alias="type"),
    granularity: Literal["month", "week"] = Query(default="month"),
) -> TrendResponse:
    result = await use_case(
        GetSpendTrendCommand(
            user_id=identity.user_id,
            currency=currency,
            type_=tx_type,
            bucket_count=months,
            granularity=granularity,
        )
    )
    return TrendResponse(
        points=[TrendPoint(month=b.label, total=str(b.total)) for b in result.buckets]
    )
