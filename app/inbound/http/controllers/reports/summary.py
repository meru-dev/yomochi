from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Query, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.transactions.use_cases.get_budget_summary import (
    GetBudgetSummaryCommand,
    GetBudgetSummaryUseCase,
)

router = ErrorAwareRouter()


class CurrencyTotal(BaseModel):
    currency: str
    total: str
    count: int


class SummaryResponse(BaseModel):
    expenses: list[CurrencyTotal]
    income: list[CurrencyTotal]


@router.get("/summary", status_code=status.HTTP_200_OK, response_model=SummaryResponse)
@inject
async def get_summary(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[GetBudgetSummaryUseCase],
    year: int = Query(),
    month: int = Query(),
) -> SummaryResponse:
    result = await use_case(
        GetBudgetSummaryCommand(user_id=identity.user_id, year=year, month=month)
    )
    return SummaryResponse(
        expenses=[
            CurrencyTotal(currency=t.currency, total=str(t.total), count=t.count)
            for t in result.expenses
        ],
        income=[
            CurrencyTotal(currency=t.currency, total=str(t.total), count=t.count)
            for t in result.income
        ],
    )
