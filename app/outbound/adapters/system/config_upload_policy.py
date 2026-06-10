from app.application.ingestion.ports.upload_policy import UploadPolicy
from app.domain.exceptions.domain_errors import FileTooLargeError


class ConfigUploadPolicy(UploadPolicy):
    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def validate(self, size_bytes: int, mime_type: str) -> None:
        if size_bytes > self._max_bytes:
            raise FileTooLargeError(size_bytes=size_bytes, max_bytes=self._max_bytes)
