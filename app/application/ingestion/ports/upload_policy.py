from abc import abstractmethod
from typing import Protocol


class UploadPolicy(Protocol):
    @abstractmethod
    def validate(self, size_bytes: int, mime_type: str) -> None:
        """Raise `FileTooLargeError` (or future policy error) when the upload
        is not acceptable. Return silently when it is."""
        ...

    @property
    @abstractmethod
    def max_bytes(self) -> int:
        """Exposed so error envelopes can quote the limit; not used for the
        decision itself."""
        ...
