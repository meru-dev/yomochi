import hashlib
import json
from typing import Any


def resolve_event_id(body: dict[str, Any]) -> str:
    """Return body's event_id, or a content hash if missing.

    Fallback to a content hash so malformed events don't share one
    idempotency key — after the first malformed event is marked processed,
    later ones with different content would otherwise be silently skipped.
    """
    event_id = body.get("event_id")
    if isinstance(event_id, str) and event_id:
        return event_id
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
