import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.application.insights.ports.insight_repository import (
    InsightAlreadyTerminalError,
    InsightNotFoundError,
)
from app.application.insights.ports.work_unit import InsightWorkUnit
from app.application.insights.use_cases.process_insight import (
    ProcessInsightCommand,
    ProcessInsightUseCase,
)
from app.domain.value_objects.enums import InsightStatus

pytestmark = pytest.mark.asyncio


def _make_uc(claim_side_effect: Exception):
    insight_repo = AsyncMock()
    insight_repo.claim_for_processing = AsyncMock(side_effect=claim_side_effect)
    insight_repo.get_by_id = AsyncMock(return_value=None)
    insight_repo.save = AsyncMock()

    uow = InsightWorkUnit(
        insight_repo=insight_repo,
        budget_reader=AsyncMock(),
    )

    @asynccontextmanager
    async def _scope():
        yield uow

    def factory():
        return _scope()

    return ProcessInsightUseCase(
        work_unit_factory=factory,
        ai_client=AsyncMock(),
    )


async def test_process_insight_on_completed_insight_returns_terminal_skip() -> None:
    uc = _make_uc(InsightAlreadyTerminalError(InsightStatus.COMPLETED))
    result = await uc(
        ProcessInsightCommand(insight_id=str(uuid.uuid4()), user_id=str(uuid.uuid4()))
    )
    assert result.terminal_skip is True


async def test_process_insight_on_failed_insight_returns_terminal_skip() -> None:
    uc = _make_uc(InsightAlreadyTerminalError(InsightStatus.FAILED))
    result = await uc(
        ProcessInsightCommand(insight_id=str(uuid.uuid4()), user_id=str(uuid.uuid4()))
    )
    assert result.terminal_skip is True


async def test_process_insight_truly_missing_row_raises_not_found() -> None:
    uc = _make_uc(InsightNotFoundError("missing"))
    with pytest.raises(InsightNotFoundError):
        await uc(ProcessInsightCommand(insight_id=str(uuid.uuid4()), user_id=str(uuid.uuid4())))
