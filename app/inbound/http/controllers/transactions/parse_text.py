from datetime import date

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel, Field

from app.application.common.ports.identity_context import IdentityContext
from app.application.transactions.use_cases.parse_transaction_text import (
    ParseTransactionTextQuery,
    ParseTransactionTextUseCase,
)

router = ErrorAwareRouter()


class ParseTransactionTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class DraftTransactionResponse(BaseModel):
    amount: str | None
    currency: str | None
    merchant: str | None
    transaction_type: str | None
    date: date | None
    suggested_category_id: str | None
    confidence: float
    requires_review: bool
    low_confidence_fields: list[str]


@router.post("/parse-text", response_model=DraftTransactionResponse, status_code=status.HTTP_200_OK)
@inject
async def parse_transaction_text(
    body: ParseTransactionTextRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ParseTransactionTextUseCase],
) -> DraftTransactionResponse:
    result = await use_case(
        ParseTransactionTextQuery(
            user_id=identity.user_id,
            text=body.text,
        )
    )
    d = result.draft
    return DraftTransactionResponse(
        amount=d.amount,
        currency=d.currency,
        merchant=d.merchant,
        transaction_type=d.transaction_type,
        date=d.date,
        suggested_category_id=d.suggested_category_id,
        confidence=d.confidence,
        requires_review=d.requires_review,
        low_confidence_fields=list(d.low_confidence_fields),
    )
