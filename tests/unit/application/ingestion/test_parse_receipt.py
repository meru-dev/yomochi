from decimal import Decimal

import pytest

from app.application.ingestion.ports.receipt_extractor import ReceiptExtractionFailedError
from app.application.ingestion.use_cases.parse_receipt import (
    ParseReceiptCommand,
    ParseReceiptUseCase,
)
from app.domain.exceptions.domain_errors import FileTooLargeError
from app.domain.value_objects.parsed_receipt import ParsedReceiptDraft


class FakePreprocessor:
    def __init__(self, result_bytes: bytes = b"compressed", result_mime: str = "image/jpeg"):
        self.result = (result_bytes, result_mime)
        self.calls: list[tuple[bytes, str]] = []

    async def preprocess(self, image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
        self.calls.append((image_bytes, mime_type))
        return self.result


class FakeExtractor:
    def __init__(self, draft: ParsedReceiptDraft | None = None, fail: bool = False):
        self._draft = draft
        self._fail = fail
        self.calls: list[tuple[bytes, str]] = []

    async def extract(self, image_bytes: bytes, mime_type: str) -> ParsedReceiptDraft:
        self.calls.append((image_bytes, mime_type))
        if self._fail:
            raise ReceiptExtractionFailedError("not a receipt")
        assert self._draft is not None
        return self._draft


class FakeUploadPolicy:
    def __init__(self, max_bytes: int = 5 * 1024 * 1024) -> None:
        self._max = max_bytes

    @property
    def max_bytes(self) -> int:
        return self._max

    def validate(self, size_bytes: int, mime_type: str) -> None:
        if size_bytes > self._max:
            raise FileTooLargeError(size_bytes=size_bytes, max_bytes=self._max)


_SAMPLE_DRAFT = ParsedReceiptDraft(
    merchant="AEON",
    amount=Decimal("1498"),
    currency="JPY",
    date_str="2026-05-29",
    suggested_category_code="groceries",
)


def _make_uc(preprocessor, extractor, policy=None):
    return ParseReceiptUseCase(
        preprocessor=preprocessor,
        extractor=extractor,
        upload_policy=policy or FakeUploadPolicy(),
    )


@pytest.mark.asyncio
async def test_parse_receipt_success():
    preprocessor = FakePreprocessor(result_bytes=b"jpeg_data", result_mime="image/jpeg")
    extractor = FakeExtractor(draft=_SAMPLE_DRAFT)
    uc = _make_uc(preprocessor, extractor)

    result = await uc(
        ParseReceiptCommand(user_id="user-1", image_bytes=b"raw", mime_type="image/heic")
    )

    assert result == _SAMPLE_DRAFT
    assert preprocessor.calls == [(b"raw", "image/heic")]
    assert extractor.calls == [(b"jpeg_data", "image/jpeg")]


@pytest.mark.asyncio
async def test_parse_receipt_preprocesses_before_extract():
    preprocessor = FakePreprocessor(result_bytes=b"processed", result_mime="image/jpeg")
    extractor = FakeExtractor(draft=_SAMPLE_DRAFT)
    uc = _make_uc(preprocessor, extractor)

    await uc(ParseReceiptCommand(user_id="u", image_bytes=b"orig", mime_type="image/png"))

    assert extractor.calls[0][0] == b"processed"


@pytest.mark.asyncio
async def test_parse_receipt_propagates_extraction_error():
    preprocessor = FakePreprocessor()
    extractor = FakeExtractor(fail=True)
    uc = _make_uc(preprocessor, extractor)

    with pytest.raises(ReceiptExtractionFailedError):
        await uc(ParseReceiptCommand(user_id="u", image_bytes=b"x", mime_type="image/jpeg"))


@pytest.mark.asyncio
async def test_parse_receipt_rejects_oversize_upload():
    preprocessor = FakePreprocessor()
    extractor = FakeExtractor(draft=_SAMPLE_DRAFT)
    policy = FakeUploadPolicy(max_bytes=10)
    uc = _make_uc(preprocessor, extractor, policy=policy)

    with pytest.raises(FileTooLargeError):
        await uc(ParseReceiptCommand(user_id="u", image_bytes=b"x" * 100, mime_type="image/jpeg"))
    assert preprocessor.calls == []
    assert extractor.calls == []
