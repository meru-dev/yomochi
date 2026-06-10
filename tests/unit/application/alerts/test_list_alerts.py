from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.alerts.use_cases.list_alerts import ListAlertsQuery, ListAlertsUseCase
from app.domain.entities.alert import Alert, AlertType
from app.domain.value_objects.ids import AlertId, UserId


def _alert(i: int = 0) -> Alert:
    return Alert(
        id_=AlertId(uuid4()),
        user_id=UserId(uuid4()),
        alert_type=AlertType.SPENDING_SPIKE,
        title=f"Alert {i}",
        body="body",
        metadata={},
        period_year=2026,
        period_month=5,
        is_read=False,
        created_at=datetime(2026, 5, i + 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_returns_empty_list_and_zero_unread():
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=[])
    repo.unread_count = AsyncMock(return_value=0)
    uc = ListAlertsUseCase(repo)
    result = await uc(ListAlertsQuery(user_id=UserId(uuid4())))
    assert result.alerts == ()
    assert result.unread_count == 0
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_sets_next_cursor_when_full_page():
    alerts = [_alert(i) for i in range(5)]
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=alerts)
    repo.unread_count = AsyncMock(return_value=2)
    uc = ListAlertsUseCase(repo)
    result = await uc(ListAlertsQuery(user_id=UserId(uuid4()), limit=5))
    assert result.next_cursor is not None
    assert result.unread_count == 2


@pytest.mark.asyncio
async def test_no_next_cursor_when_partial_page():
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=[_alert()])
    repo.unread_count = AsyncMock(return_value=1)
    uc = ListAlertsUseCase(repo)
    result = await uc(ListAlertsQuery(user_id=UserId(uuid4()), limit=20))
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_cursor_passed_to_repo_when_provided():
    """Cursor is decoded and forwarded to repo.list_for_user as (datetime, AlertId) tuple."""
    from app.application.alerts.use_cases.list_alerts import _encode_cursor

    first_page_alert = _alert(0)
    cursor_str = _encode_cursor(first_page_alert)

    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=[])
    repo.unread_count = AsyncMock(return_value=0)
    uc = ListAlertsUseCase(repo)
    await uc(ListAlertsQuery(user_id=UserId(uuid4()), limit=20, cursor=cursor_str))

    call_args = repo.list_for_user.call_args
    cursor_arg = call_args.kwargs.get("cursor") or call_args.args[2]
    assert cursor_arg is not None
    decoded_dt, decoded_id = cursor_arg
    assert decoded_id == first_page_alert.id_
    assert decoded_dt == first_page_alert.created_at


@pytest.mark.asyncio
async def test_limit_zero_does_not_raise():
    """unread-count controller calls with limit=0; next_cursor must be None, not IndexError."""
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=[])
    repo.unread_count = AsyncMock(return_value=3)
    uc = ListAlertsUseCase(repo)
    result = await uc(ListAlertsQuery(user_id=UserId(uuid4()), limit=0))
    assert result.next_cursor is None
    assert result.unread_count == 3
