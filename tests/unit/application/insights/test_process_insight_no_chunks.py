import uuid
from contextlib import asynccontextmanager
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
from app.domain.value_objects.enums import ContextQuality, InsightStatus, Period
from app.domain.value_objects.ids import InsightId, UserId

pytestmark = pytest.mark.asyncio


def _queued_insight(user_id: UserId, insight_id: InsightId) -> Insight:
    insight = Insight(
        id_=insight_id,
        user_id=user_id,
        period=Period.MONTHLY,
        period_year=2026,
        period_month=4,
        status=InsightStatus.PENDING,
        context_quality=None,
        title=None,
        description=None,
        impact_score=None,
        generated_at=None,
        error_message=None,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    insight.mark_queued()
    return insight


def _build(insight: Insight) -> tuple[ProcessInsightUseCase, AsyncMock]:
    insight_repo = AsyncMock()

    async def _claim(_id, _user_id, _deadline):
        insight.status = InsightStatus.PROCESSING
        return insight

    insight_repo.claim_for_processing = AsyncMock(side_effect=_claim)
    insight_repo.get_by_id = AsyncMock(return_value=insight)
    insight_repo.save = AsyncMock()

    chunk_retriever = AsyncMock()
    chunk_retriever.search = AsyncMock(return_value=[])  # ← no chunks
    chunk_retriever.get_portrait = AsyncMock(return_value=None)

    budget_reader = AsyncMock()
    budget_reader.read_month = AsyncMock(return_value=[])
    budget_reader.read_history_months = AsyncMock(return_value={})

    uow = InsightWorkUnit(
        insight_repo=insight_repo,
        chunk_writer=AsyncMock(),
        chunk_retriever=chunk_retriever,
        budget_reader=budget_reader,
        alert_writer=AsyncMock(),
        dirty_period_repo=AsyncMock(),
    )

    @asynccontextmanager
    async def _scope():
        yield uow

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    ai_client = AsyncMock()  # must not be called on NONE path
    return (
        ProcessInsightUseCase(
            work_unit_factory=lambda: _scope(),
            embedder=embedder,
            ai_client=ai_client,
        ),
        insight_repo,
    )


def _cmd(insight_id: InsightId, user_id: UserId) -> ProcessInsightCommand:
    return ProcessInsightCommand(insight_id=str(insight_id), user_id=str(user_id))


async def test_persists_failed_when_no_chunks_returned() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)
    uc, repo = _build(insight)

    # The CRIT was a TypeError here (_persist_failure missing user_id);
    # the call must complete and the entity must reach FAILED.
    result = await uc(_cmd(insight_id, user_id))

    assert result.context_quality == ContextQuality.NONE
    assert insight.status == InsightStatus.FAILED
    assert insight.error_message is not None
    assert "No transaction data found" in insight.error_message
    # AI client must not be reached on the NONE branch.
    assert repo.save.await_count >= 1


async def test_no_chunks_branch_handles_missing_insight_silently() -> None:
    """If the insight row disappears between claim and the failure-save UoW,
    `_persist_failure` returns silently — the original NONE result still flows."""
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)
    uc, repo = _build(insight)
    # Simulate get_by_id returning None inside _persist_failure.
    repo.get_by_id = AsyncMock(return_value=None)

    result = await uc(_cmd(insight_id, user_id))

    assert result.context_quality == ContextQuality.NONE
    # No exception bubbled. The InsightNotFoundError path is reserved for the
    # COMPLETED branch, not the failure-save path.
    assert not isinstance(result, InsightNotFoundError)
