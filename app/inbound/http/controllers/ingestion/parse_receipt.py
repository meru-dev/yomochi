from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, UploadFile, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.ingestion.use_cases.parse_receipt import (
    ParseReceiptCommand,
    ParseReceiptUseCase,
)

router = ErrorAwareRouter()

_ALLOWED_IMAGE_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/heic",
        "image/heif",
    }
)

_MAX_RECEIPT_BYTES = 10 * 1024 * 1024  # 10 MB — keep in sync with NGINX client_max_body_size


class ParsedReceiptResponse(BaseModel):
    merchant: str | None
    merchant_type: str | None
    amount: str | None
    currency: str | None
    date: str | None
    suggested_category_code: str | None
    notes: str | None


@router.post(
    "/ingestion/parse-receipt",
    status_code=status.HTTP_200_OK,
    response_model=ParsedReceiptResponse,
)
@inject
async def parse_receipt(
    file: UploadFile,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ParseReceiptUseCase],
) -> ParsedReceiptResponse:
    mime = file.content_type
    if mime is None or mime not in _ALLOWED_IMAGE_MIME:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported file type: {mime or 'unspecified'}. Accepted: JPEG, PNG, WebP, GIF, HEIC, HEIF.",
        )

    data = await file.read(_MAX_RECEIPT_BYTES + 1)
    if len(data) > _MAX_RECEIPT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 10 MB limit.",
        )

    # FileTooLargeError + ReceiptExtractionFailedError propagate to global handlers.
    draft = await use_case(
        ParseReceiptCommand(
            user_id=str(identity.user_id),
            image_bytes=data,
            mime_type=mime,
        )
    )

    return ParsedReceiptResponse(
        merchant=draft.merchant,
        merchant_type=draft.merchant_type,
        amount=str(draft.amount) if draft.amount is not None else None,
        currency=draft.currency,
        date=draft.date_str,
        suggested_category_code=draft.suggested_category_code,
        notes=draft.notes,
    )
