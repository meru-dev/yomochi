import pytest

from app.application.common.cursor import decode_cursor, encode_cursor
from app.domain.exceptions.domain_errors import InvalidCursorError


def test_encode_decode_roundtrip() -> None:
    payload = {"created_at": "2026-06-01T00:00:00+00:00", "id": "abc-123"}
    assert decode_cursor(encode_cursor(payload)) == payload


def test_decode_raises_invalid_cursor_on_garbage() -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor("not-valid-base64!!!")


def test_decode_raises_invalid_cursor_on_truncated() -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor("dGhpcyBpcyBub3QganNvbg==")  # "this is not json"


def test_encode_is_url_safe() -> None:
    token = encode_cursor({"x": "a" * 100})
    assert "+" not in token
    assert "/" not in token
