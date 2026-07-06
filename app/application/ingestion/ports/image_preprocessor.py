from abc import abstractmethod
from typing import Protocol


class ImagePreprocessor(Protocol):
    @abstractmethod
    async def preprocess(self, image_bytes: bytes, mime_type: str) -> tuple[bytes, str]: ...
