from dataclasses import dataclass

from app.application.ingestion.ports.image_preprocessor import ImagePreprocessor
from app.application.ingestion.ports.receipt_extractor import ReceiptExtractor
from app.application.ingestion.ports.upload_policy import UploadPolicy
from app.domain.value_objects.parsed_receipt import ParsedReceiptDraft


@dataclass(frozen=True, slots=True)
class ParseReceiptCommand:
    user_id: str
    image_bytes: bytes
    mime_type: str


class ParseReceiptUseCase:
    def __init__(
        self,
        preprocessor: ImagePreprocessor,
        extractor: ReceiptExtractor,
        upload_policy: UploadPolicy,
    ) -> None:
        self._preprocessor = preprocessor
        self._extractor = extractor
        self._upload_policy = upload_policy

    async def __call__(self, command: ParseReceiptCommand) -> ParsedReceiptDraft:
        self._upload_policy.validate(len(command.image_bytes), command.mime_type)
        compressed_bytes, compressed_mime = await self._preprocessor.preprocess(
            command.image_bytes, command.mime_type
        )
        return await self._extractor.extract(compressed_bytes, compressed_mime)
