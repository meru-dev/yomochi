import base64
import json

import pytest

from app.domain.exceptions.domain_errors import InvalidCursorError


def test_transactions_decode_cursor_raises_on_garbage():
    from app.application.transactions.use_cases.list_transactions import decode_cursor

    with pytest.raises(InvalidCursorError):
        decode_cursor("not-base64!!!")


def test_transactions_decode_cursor_raises_on_missing_fields():
    bad = base64.urlsafe_b64encode(json.dumps({"date": "2024-01-01"}).encode()).decode()
    from app.application.transactions.use_cases.list_transactions import decode_cursor

    with pytest.raises(InvalidCursorError):
        decode_cursor(bad)


def test_insights_decode_cursor_raises_on_garbage():
    from app.application.insights.use_cases.list_insights import _decode_cursor

    with pytest.raises(InvalidCursorError):
        _decode_cursor("!!!")


def test_audit_events_decode_cursor_raises_on_garbage():
    from app.application.users.use_cases.list_audit_events import _decode_cursor

    with pytest.raises(InvalidCursorError):
        _decode_cursor("!!!")
