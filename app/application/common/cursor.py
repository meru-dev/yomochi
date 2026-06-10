import base64
import json
from typing import Any

from app.domain.exceptions.domain_errors import InvalidCursorError


def encode_cursor(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(raw: str) -> dict[str, Any]:
    try:
        return json.loads(base64.urlsafe_b64decode(raw.encode()).decode())  # type: ignore[no-any-return]
    except Exception as exc:
        raise InvalidCursorError("Invalid or expired pagination cursor") from exc
