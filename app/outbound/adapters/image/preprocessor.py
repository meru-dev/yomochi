import asyncio
import io

import pillow_heif
import structlog
from PIL import Image

logger = structlog.get_logger(__name__)

pillow_heif.register_heif_opener()


class PillowImagePreprocessor:
    __slots__ = ("_jpeg_quality", "_max_dimension", "_semaphore")

    def __init__(
        self,
        semaphore: asyncio.Semaphore,
        max_dimension: int,
        jpeg_quality: int,
    ) -> None:
        self._semaphore = semaphore
        self._max_dimension = max_dimension
        self._jpeg_quality = jpeg_quality

    async def preprocess(self, image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
        async with self._semaphore:
            return await asyncio.to_thread(self._sync_preprocess, image_bytes)

    def _sync_preprocess(self, image_bytes: bytes) -> tuple[bytes, str]:
        opened: Image.Image = Image.open(io.BytesIO(image_bytes))
        img: Image.Image = opened.convert("RGB")
        w, h = img.size
        if max(w, h) > self._max_dimension:
            ratio = self._max_dimension / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self._jpeg_quality, optimize=True)
        return buf.getvalue(), "image/jpeg"
