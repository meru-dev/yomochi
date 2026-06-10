from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.insights.use_cases.get_insight import (
    GetInsightQuery,
    GetInsightUseCase,
    InsightNotFoundError,
)
from app.domain.entities.insight import Insight
from app.domain.value_objects.ids import InsightId

router = ErrorAwareRouter()


class CurrencyTotalsResponse(BaseModel):
    currency: str
    income: str
    expense: str
    count: int


class InsightResponse(BaseModel):
    id: str
    period: str
    period_year: int
    period_month: int
    status: str
    context_quality: str | None
    title: str | None
    description: str | None
    impact_score: int | None
    generated_at: str | None
    error_message: str | None
    created_at: str
    partial_context_warning: bool
    budget_summary: list[CurrencyTotalsResponse] | None


def _serialize(insight: Insight) -> InsightResponse:
    cq = insight.context_quality
    bs = insight.budget_summary
    return InsightResponse(
        id=str(insight.id_),
        period=insight.period.value,
        period_year=insight.period_year,
        period_month=insight.period_month,
        status=insight.status.value,
        context_quality=cq.value if cq else None,
        title=insight.title,
        description=insight.description,
        impact_score=insight.impact_score,
        generated_at=insight.generated_at.isoformat() if insight.generated_at else None,
        error_message=insight.error_message,
        created_at=insight.created_at.isoformat(),
        partial_context_warning=cq is not None and cq.value in ("partial", "none"),
        budget_summary=(
            [
                CurrencyTotalsResponse(
                    currency=ct.currency,
                    income=str(ct.income),
                    expense=str(ct.expense),
                    count=ct.count,
                )
                for ct in bs.per_currency
            ]
            if bs is not None
            else None
        ),
    )


@router.get(
    "/{insight_id}",
    status_code=status.HTTP_200_OK,
    response_model=InsightResponse,
    error_map={InsightNotFoundError: status.HTTP_404_NOT_FOUND},
)
@inject
async def get_insight(
    insight_id: UUID,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[GetInsightUseCase],
) -> InsightResponse:
    insight = await use_case(
        GetInsightQuery(
            insight_id=InsightId(insight_id),
            user_id=identity.user_id,
        )
    )
    return _serialize(insight)
