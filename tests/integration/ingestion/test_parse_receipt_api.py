from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pillow_heif
import pytest
from httpx import AsyncClient
from PIL import Image

from app.application.ingestion.ports.receipt_extractor import ReceiptExtractionFailedError
from app.domain.value_objects.parsed_receipt import ParsedReceiptDraft
from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")

_URL = "/api/v1/ingestion/parse-receipt"


def _make_tiny_jpeg() -> bytes:
    img = Image.new("RGB", (50, 50), color=(200, 100, 50))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_tiny_heic() -> bytes:
    img = Image.new("RGB", (50, 50), color=(200, 100, 50))
    heif = pillow_heif.from_pillow(img)
    buf = BytesIO()
    heif.save(buf, format="HEIF")
    return buf.getvalue()


def _make_draft() -> ParsedReceiptDraft:
    return ParsedReceiptDraft(
        merchant="Test Store",
        amount=Decimal("500"),
        currency="JPY",
        date_str="2026-05-29",
        suggested_category_code="food",
        line_items=({"name": "Coffee", "price": "500"},),
    )


async def test_parse_receipt_returns_draft(client: AsyncClient) -> None:
    await register_and_login(client, email="receipt-ok@example.com")

    with patch(
        "app.outbound.adapters.openai.receipt_extractor.OpenAIReceiptExtractor.extract",
        new_callable=AsyncMock,
        return_value=_make_draft(),
    ):
        resp = await client.post(
            _URL,
            files={"file": ("receipt.jpg", _make_tiny_jpeg(), "image/jpeg")},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["merchant"] == "Test Store"
    assert body["amount"] == "500"
    assert body["currency"] == "JPY"
    assert "Coffee" in body["notes"]
    assert body["suggested_category_code"] == "food"


async def test_parse_receipt_accepts_iphone_heic(client: AsyncClient) -> None:
    await register_and_login(client, email="receipt-heic@example.com")

    with patch(
        "app.outbound.adapters.openai.receipt_extractor.OpenAIReceiptExtractor.extract",
        new_callable=AsyncMock,
        return_value=_make_draft(),
    ):
        resp = await client.post(
            _URL,
            files={"file": ("receipt.heic", _make_tiny_heic(), "image/heic")},
        )

    assert resp.status_code == 200, resp.text


async def test_parse_receipt_rejects_oversized(client: AsyncClient) -> None:
    await register_and_login(client, email="receipt-big@example.com")
    big_data = b"x" * (6 * 1024 * 1024)  # 6 MB > 5 MB limit
    resp = await client.post(
        _URL,
        files={"file": ("big.jpg", big_data, "image/jpeg")},
    )
    assert resp.status_code == 413, resp.text


async def test_parse_receipt_returns_422_for_non_receipt_image(client: AsyncClient) -> None:
    await register_and_login(client, email="receipt-notreceipt@example.com")

    with patch(
        "app.outbound.adapters.openai.receipt_extractor.OpenAIReceiptExtractor.extract",
        new_callable=AsyncMock,
        side_effect=ReceiptExtractionFailedError("Image does not appear to be a receipt"),
    ):
        resp = await client.post(
            _URL,
            files={"file": ("selfie.jpg", _make_tiny_jpeg(), "image/jpeg")},
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error"]["code"] == "ingestion.parse_failed"


async def test_parse_receipt_requires_auth(client: AsyncClient) -> None:
    # No login — fresh client has no session cookie
    resp = await client.post(
        _URL,
        files={"file": ("receipt.jpg", _make_tiny_jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 401, resp.text


async def test_parse_receipt_rejects_missing_content_type(client: AsyncClient) -> None:
    """Previously the controller defaulted a missing content-type to image/jpeg,
    which then propagated to the OpenAI vision call with a lying MIME header.
    The fix is to reject the upload with 422 instead."""
    await register_and_login(client, email="receipt-no-mime@example.com")
    # An explicit empty string for content_type means "no MIME header" in httpx.
    resp = await client.post(
        _URL,
        files={"file": ("receipt.jpg", _make_tiny_jpeg(), "")},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    detail = body.get("detail") or body.get("error", {}).get("message", "")
    assert "Unsupported file type" in str(detail) or "unspecified" in str(detail).lower()


async def test_parse_receipt_rejects_pdf_mime(client: AsyncClient) -> None:
    """Defense-in-depth for the same controller branch: a PDF MIME is not in
    the allow-list and must be rejected without reaching the extractor."""
    await register_and_login(client, email="receipt-pdf@example.com")
    resp = await client.post(
        _URL,
        files={"file": ("receipt.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert resp.status_code == 422, resp.text
