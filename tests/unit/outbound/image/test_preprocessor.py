import asyncio
import io
from concurrent.futures import ThreadPoolExecutor

import pillow_heif
import pytest
from PIL import Image

from app.outbound.adapters.image.preprocessor import PillowImagePreprocessor


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_preprocessor(max_dimension: int = 1568) -> PillowImagePreprocessor:
    return PillowImagePreprocessor(
        semaphore=asyncio.Semaphore(1),
        max_dimension=max_dimension,
        jpeg_quality=85,
        thread_pool=ThreadPoolExecutor(max_workers=1),
    )


@pytest.mark.asyncio
async def test_preprocess_jpeg_returns_jpeg():
    proc = _make_preprocessor()
    result_bytes, mime = await proc.preprocess(_make_jpeg(), "image/jpeg")
    assert mime == "image/jpeg"
    img = Image.open(io.BytesIO(result_bytes))
    assert img.format == "JPEG"


@pytest.mark.asyncio
async def test_preprocess_large_image_is_resized():
    proc = _make_preprocessor(max_dimension=100)
    result_bytes, _ = await proc.preprocess(_make_jpeg(width=500, height=300), "image/jpeg")
    img = Image.open(io.BytesIO(result_bytes))
    assert max(img.size) <= 100


@pytest.mark.asyncio
async def test_preprocess_small_image_not_upscaled():
    proc = _make_preprocessor(max_dimension=1568)
    small = _make_jpeg(width=50, height=50)
    result_bytes, _ = await proc.preprocess(small, "image/jpeg")
    img = Image.open(io.BytesIO(result_bytes))
    assert img.size == (50, 50)


@pytest.mark.asyncio
async def test_preprocess_strips_exif():
    proc = _make_preprocessor()
    result_bytes, _ = await proc.preprocess(_make_jpeg(), "image/jpeg")
    img = Image.open(io.BytesIO(result_bytes))
    assert img.info.get("exif") is None


def _make_heic(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(200, 100, 50))
    heif = pillow_heif.from_pillow(img)
    buf = io.BytesIO()
    heif.save(buf, format="HEIF")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_preprocess_heic_iphone_format_returns_jpeg():
    proc = _make_preprocessor()
    result_bytes, mime = await proc.preprocess(_make_heic(), "image/heic")
    assert mime == "image/jpeg"
    img = Image.open(io.BytesIO(result_bytes))
    assert img.format == "JPEG"


@pytest.mark.asyncio
async def test_preprocess_converts_palette_to_rgb():
    # PNG palette mode image
    buf = io.BytesIO()
    Image.new("P", (50, 50)).save(buf, format="PNG")
    proc = _make_preprocessor()
    result_bytes, mime = await proc.preprocess(buf.getvalue(), "image/png")
    assert mime == "image/jpeg"
    img = Image.open(io.BytesIO(result_bytes))
    assert img.mode == "RGB"
