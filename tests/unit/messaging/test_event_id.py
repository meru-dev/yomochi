import hashlib
import json

from app.inbound.messaging._event_id import resolve_event_id


def _expected_hash(body: dict) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def test_returns_event_id_when_present() -> None:
    body = {"event_id": "abc-123", "event_type": "SomethingHappened"}
    assert resolve_event_id(body) == "abc-123"


def test_returns_content_hash_when_event_id_missing() -> None:
    body = {"event_type": "Malformed", "payload": {}}
    result = resolve_event_id(body)
    # Hardcoded digest for {"event_type":"Malformed","payload":{}} (sort_keys, no spaces)
    assert result == "0f5181af09c10fca3413a21b519f8c1599c76e7681634a7d07994d2d1fd86a3c"


def test_returns_content_hash_when_event_id_none() -> None:
    body = {"event_id": None}
    result = resolve_event_id(body)
    # Hardcoded digest for {"event_id":null}
    assert result == "c4e9ee7ba30037d69426a1cb9fd9d96550383fdf4eec16c8c95a8ba20c52fa7a"


def test_returns_content_hash_when_event_id_empty_string() -> None:
    body = {"event_id": "", "event_type": "Malformed"}
    result = resolve_event_id(body)
    assert result == _expected_hash(body)


def test_two_different_malformed_bodies_get_different_keys() -> None:
    body_a = {"event_type": "Malformed", "payload": {"amount": 10}}
    body_b = {"event_type": "Malformed", "payload": {"amount": 20}}
    assert resolve_event_id(body_a) != resolve_event_id(body_b)


def test_non_string_event_id_falls_back_to_hash() -> None:
    body = {"event_id": 12345, "event_type": "Bad"}
    result = resolve_event_id(body)
    assert result == _expected_hash(body)
