import contextlib
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.insights.ports.insight_repository import InsightNotFoundError
from app.application.insights.ports.work_unit import InsightWorkUnit
from app.application.insights.use_cases.process_insight import (
    ProcessInsightCommand,
    ProcessInsightUseCase,
)
from app.domain.entities.insight import Insight
from app.domain.value_objects.enums import (
    InsightStatus,
    Period,
)
from app.domain.value_objects.ids import InsightId, UserId

pytestmark = pytest.mark.asyncio


def _make_use_case(
    *,
    owner_id: UserId,
    insight: Insight,
) -> ProcessInsightUseCase:
    """Build a use case whose repo only honours the correct owner."""
    insight_repo = AsyncMock()

    async def _claim(claimed_id: InsightId, claimed_user: UserId, _deadline: object) -> Insight:
        if claimed_user != owner_id:
            raise InsightNotFoundError(str(claimed_id))
        insight.status = InsightStatus.PROCESSING
        return insight

    insight_repo.claim_for_processing = AsyncMock(side_effect=_claim)
    insight_repo.get_by_id = AsyncMock(return_value=insight)
    insight_repo.save = AsyncMock()

    uow = InsightWorkUnit(
        insight_repo=insight_repo,
        budget_reader=AsyncMock(),
    )

    class _Factory:
        def __call__(self) -> "_Factory":
            return self

        async def __aenter__(self) -> InsightWorkUnit:
            return uow

        async def __aexit__(self, *_a: object) -> None:
            return None

    return ProcessInsightUseCase(
        work_unit_factory=_Factory(),  # type: ignore[arg-type]
        ai_client=AsyncMock(),
    )


def _queued_insight(user_id: UserId, insight_id: InsightId) -> Insight:
    return Insight(
        id_=insight_id,
        user_id=user_id,
        period=Period.MONTHLY,
        period_year=2026,
        period_month=6,
        status=InsightStatus.QUEUED,
        context_quality=None,
        title=None,
        description=None,
        impact_score=None,
        generated_at=None,
        error_message=None,
        created_at=datetime.now(UTC),
    )


async def test_wrong_owner_in_command_rejected_at_claim() -> None:
    real_owner = UserId(uuid.uuid4())
    attacker = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(real_owner, insight_id)

    uc = _make_use_case(owner_id=real_owner, insight=insight)
    cmd = ProcessInsightCommand(
        insight_id=str(insight_id),
        user_id=str(attacker),  # forged
    )

    with pytest.raises(InsightNotFoundError):
        await uc(cmd)

    # Row never claimed.
    assert insight.status is InsightStatus.QUEUED


async def test_correct_owner_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    real_owner = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(real_owner, insight_id)

    uc = _make_use_case(owner_id=real_owner, insight=insight)
    cmd = ProcessInsightCommand(
        insight_id=str(insight_id),
        user_id=str(real_owner),
    )

    # The claim succeeds. The pipeline still fails downstream because we
    # haven't wired chunks — that's not what we're asserting; we only need to
    # confirm claim succeeded i.e. status moved off QUEUED.
    with contextlib.suppress(Exception):
        await uc(cmd)

    assert insight.status in {
        InsightStatus.PROCESSING,
        InsightStatus.FAILED,
        InsightStatus.COMPLETED,
    }
    assert insight.status is not InsightStatus.QUEUED
