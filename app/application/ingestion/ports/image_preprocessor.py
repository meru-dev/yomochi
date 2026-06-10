from abc import abstractmethod
from typing import Protocol


class ImagePreprocessor(Protocol):
    @abstractmethod
    async def preprocess(self, image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
        """Normalize image: resize, convert to JPEG, strip EXIF. Returns (bytes, mime_type)."""
        ...
