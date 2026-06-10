from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel, Field

from app.application.common.ports.identity_context import IdentityContext
from app.application.search.use_cases.search_transactions import SearchTransactionsUseCase
from app.domain.entities.transaction import Transaction

router = ErrorAwareRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


class SearchTransactionItem(BaseModel):
    id: str
    amount: str
    currency: str
    date: str
    type: str
    merchant: str | None
    notes: str | None


class SearchResponse(BaseModel):
    items: list[SearchTransactionItem]


def _serialize(t: Transaction) -> SearchTransactionItem:
    return SearchTransactionItem(
        id=str(t.id_.value),
        amount=str(t.amount.amount),
        currency=t.amount.currency.code,
        date=t.date.isoformat(),
        type=t.type_.value,
        merchant=t.merchant,
        notes=t.notes,
    )


@router.post("", status_code=status.HTTP_200_OK, response_model=SearchResponse)
@inject
async def search_transactions(
    body: SearchRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[SearchTransactionsUseCase],
) -> SearchResponse:
    transactions = await use_case(identity.user_id, body.query, limit=body.limit)
    return SearchResponse(items=[_serialize(t) for t in transactions])


def make_search_router() -> APIRouter:
    r = APIRouter(tags=["search"])
    r.include_router(router, prefix="/search")
    return r
