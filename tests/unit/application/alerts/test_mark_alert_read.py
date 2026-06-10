from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.alerts.use_cases.mark_alert_read import (
    AlertNotFoundError,
    MarkAlertReadCommand,
    MarkAlertReadUseCase,
)
from app.domain.value_objects.ids import AlertId, UserId


@pytest.mark.asyncio
async def test_calls_repo_mark_read():
    repo = AsyncMock()
    repo.mark_read = AsyncMock(return_value=True)
    uc = MarkAlertReadUseCase(repo)
    aid = AlertId(uuid4())
    uid = UserId(uuid4())
    await uc(MarkAlertReadCommand(user_id=uid, alert_id=aid))
    repo.mark_read.assert_called_once_with(aid, uid)


@pytest.mark.asyncio
async def test_raises_not_found_when_repo_returns_false():
    repo = AsyncMock()
    repo.mark_read = AsyncMock(return_value=False)
    uc = MarkAlertReadUseCase(repo)
    with pytest.raises(AlertNotFoundError):
        await uc(MarkAlertReadCommand(user_id=UserId(uuid4()), alert_id=AlertId(uuid4())))
