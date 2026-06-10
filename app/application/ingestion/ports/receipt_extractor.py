from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.parsed_receipt import ParsedReceiptDraft


class ReceiptExtractionFailedError(Exception):
    """Raised when the image cannot be parsed as a receipt or confidence is too low."""


class ReceiptExtractor(Protocol):
    @abstractmethod
    async def extract(self, image_bytes: bytes, mime_type: str) -> ParsedReceiptDraft:
        """Extract transaction fields from a receipt image.

        Raises ReceiptExtractionFailedError if the image is not a receipt
        or critical fields (amount, currency) cannot be determined.
        """
        ...
