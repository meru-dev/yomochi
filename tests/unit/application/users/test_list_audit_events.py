from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.users.use_cases.list_audit_events import (
    AuditEventRow,
    ListAuditEventsQuery,
    ListAuditEventsUseCase,
)
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import UserId

pytestmark = pytest.mark.asyncio

_USER_ID = UserId(uuid.uuid4())

_T0 = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)


def _row(
    event_type: AuditEventType = AuditEventType.USER_LOGIN, at: datetime = _T0
) -> AuditEventRow:
    return AuditEventRow(
        id=str(uuid.uuid4()),
        event_type=event_type,
        occurred_at=at,
        ip="127.0.0.1",
        user_agent="pytest",
    )


def _make_use_case(rows: list[AuditEventRow]) -> ListAuditEventsUseCase:
    reader = MagicMock()
    reader.list_by_user = AsyncMock(return_value=rows)
    return ListAuditEventsUseCase(audit_event_reader=reader)


async def test_returns_rows_from_reader() -> None:
    rows = [_row(), _row(at=_T1)]
    uc = _make_use_case(rows)

    result = await uc(ListAuditEventsQuery(user_id=_USER_ID, limit=20))

    assert len(result.events) == 2


async def test_no_next_cursor_when_fewer_than_limit() -> None:
    rows = [_row()]
    uc = _make_use_case(rows)

    result = await uc(ListAuditEventsQuery(user_id=_USER_ID, limit=20))

    assert result.next_cursor is None


async def test_next_cursor_present_when_full_page() -> None:
    # Reader returns limit+1 rows to signal there are more pages.
    _T2 = datetime(2026, 3, 3, tzinfo=UTC)  # noqa: N806
    rows = [_row(at=_T0), _row(at=_T1), _row(at=_T2)]
    uc = _make_use_case(rows)

    result = await uc(ListAuditEventsQuery(user_id=_USER_ID, limit=2))

    assert result.next_cursor is not None
    assert len(result.events) == 2  # last row is sentinel, not returned


async def test_passes_filters_to_reader() -> None:
    reader = MagicMock()
    reader.list_by_user = AsyncMock(return_value=[])
    uc = ListAuditEventsUseCase(audit_event_reader=reader)

    query = ListAuditEventsQuery(
        user_id=_USER_ID,
        limit=10,
        event_type_filter="user_login",
        from_date=datetime(2026, 3, 1, tzinfo=UTC),
        to_date=datetime(2026, 3, 31, tzinfo=UTC),
    )
    await uc(query)

    reader.list_by_user.assert_awaited_once()
    call_kwargs = reader.list_by_user.call_args.kwargs
    assert call_kwargs["user_id"] == _USER_ID
    assert call_kwargs["limit"] == 11  # limit+1 for cursor detection
    assert call_kwargs["event_type_filter"] == "user_login"


async def test_empty_result_has_no_cursor() -> None:
    uc = _make_use_case([])
    result = await uc(ListAuditEventsQuery(user_id=_USER_ID, limit=20))
    assert result.next_cursor is None
    assert result.events == ()
