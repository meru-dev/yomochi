import base64
from decimal import Decimal, InvalidOperation

import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.application.ingestion.ports.receipt_extractor import ReceiptExtractionFailedError
from app.domain.value_objects.parsed_receipt import ParsedReceiptDraft
from app.outbound.adapters.openai._gateway import OpenAIGateway
from app.outbound.adapters.openai.pricing import estimate_cost
from app.outbound.observability.prometheus import openai_cost_usd_total, openai_tokens_total

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a receipt OCR extractor for a personal finance app.
Read the entire image carefully — receipts often have small or faded text.
Scan top-to-bottom: store name is usually at the top, totals at the bottom.

The image can be anything — a photo, screenshot, scan, handwritten note, or random picture.
Determine whether it contains a receipt or invoice (proof of a financial transaction).
If it does not, set is_receipt to false and all other fields to null.

If IS a receipt or invoice, extract all fields below.
Set a field to null only if it truly cannot be read or inferred.

TOTAL AMOUNT (critical — read carefully):
Use the amount the customer actually owed after all taxes, fees, and discounts.
  JP: 合計 / 税込合計 / お会計 / ご請求額
  EN: Total / Total Due / Amount Due / Grand Total
Do NOT use:
  - subtotals (小計 / Subtotal) — pre-tax, not final
  - cash tendered (お預かり / お預り / Cash) — customer may have overpaid
  - change (お釣り / Change) — returned to customer
If no total line is visible or legible, calculate it yourself: sum all line item prices,
then add any explicit tax amount shown. Never leave total_amount null if line items are present.

MERCHANT:
- merchant: exact name as printed (store header, top of receipt)
- merchant_type: short description of the establishment type in English
  (e.g. "convenience store", "supermarket", "restaurant", "cafe",
   "pharmacy", "electronics store", "online delivery", etc.)

OTHER FIELDS:
- currency: ISO 4217 (JPY / USD / EUR …)
- date: ISO 8601 YYYY-MM-DD
- suggested_category_code: groceries | dining | transport | entertainment |
  health | shopping | utilities | other
- line_items: up to 20 items, each with name and price string

Supported languages: Japanese, English.
"""


class _LineItem(BaseModel):
    name: str
    price: str


class _ReceiptExtraction(BaseModel):
    is_receipt: bool
    total_amount: str | None
    currency: str | None
    merchant: str | None
    merchant_type: str | None  # "combini" | "restaurant" | "other"
    date: str | None
    suggested_category_code: str | None
    line_items: list[_LineItem]


class OpenAIReceiptExtractor:
    def __init__(
        self,
        gateway: OpenAIGateway,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._timeout = timeout_seconds

    async def extract(self, image_bytes: bytes, mime_type: str) -> ParsedReceiptDraft:
        return await self._gateway.call(
            endpoint="vision",
            timeout=self._timeout,
            fn=lambda client: self._do_extract(client, image_bytes, mime_type),
        )

    async def _do_extract(
        self,
        client: AsyncOpenAI,
        image_bytes: bytes,
        mime_type: str,
    ) -> ParsedReceiptDraft:
        b64 = base64.b64encode(image_bytes).decode()
        response = await client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{b64}",
                                "detail": "high",
                            },
                        },
                        {"type": "text", "text": "Extract the receipt data."},
                    ],
                },
            ],
            response_format=_ReceiptExtraction,
            temperature=0.1,
            max_tokens=1500,
        )

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        openai_tokens_total.labels(endpoint="vision", direction="prompt").inc(prompt_tokens)
        openai_tokens_total.labels(endpoint="vision", direction="completion").inc(completion_tokens)
        cost = estimate_cost(
            self._model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
        openai_cost_usd_total.labels(endpoint="vision", model=self._model).inc(cost)

        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ReceiptExtractionFailedError(
                "OpenAI returned no structured output for vision call"
            )

        if not parsed.is_receipt:
            raise ReceiptExtractionFailedError("Image does not appear to be a receipt")

        if parsed.total_amount is None or parsed.currency is None:
            raise ReceiptExtractionFailedError(
                "Receipt parsing incomplete: amount or currency could not be determined"
            )

        try:
            amount = Decimal(parsed.total_amount)
        except InvalidOperation:
            raise ReceiptExtractionFailedError(
                f"Invalid amount format returned by model: {parsed.total_amount!r}"
            ) from None

        line_items: tuple[dict[str, str], ...] = tuple(
            {"name": item.name, "price": item.price} for item in parsed.line_items
        )

        logger.info(
            "receipt_extracted",
            merchant=parsed.merchant,
            merchant_type=parsed.merchant_type,
            amount=str(amount),
            currency=parsed.currency,
            line_items_count=len(line_items),
        )

        return ParsedReceiptDraft(
            merchant=parsed.merchant,
            amount=amount,
            currency=parsed.currency,
            date_str=parsed.date,
            suggested_category_code=parsed.suggested_category_code,
            merchant_type=parsed.merchant_type,
            line_items=line_items,
        )
