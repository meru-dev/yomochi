from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.alerts.use_cases.clear_alerts import ClearAlertsCommand, ClearAlertsUseCase
from app.domain.value_objects.ids import UserId


@pytest.mark.asyncio
async def test_calls_repo_clear_all():
    repo = AsyncMock()
    repo.clear_all = AsyncMock()
    uc = ClearAlertsUseCase(repo)
    uid = UserId(uuid4())
    await uc(ClearAlertsCommand(user_id=uid))
    repo.clear_all.assert_called_once_with(uid)
