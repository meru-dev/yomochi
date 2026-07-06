import asyncio
from collections.abc import AsyncIterator

from app.application.insights.ports.work_unit import InsightWorkUnitFactory
from app.application.insights.use_cases.get_insight import InsightNotFoundError
from app.domain.entities.insight import Insight
from app.domain.value_objects.enums import InsightStatus
from app.domain.value_objects.ids import InsightId, UserId

_TERMINAL_STATUSES = frozenset({InsightStatus.COMPLETED, InsightStatus.FAILED})


class StreamInsightUseCase:
    """Watch an insight row and yield it on every status transition.

    Generation runs out of band in the insight-worker, so this use case never
    sees LLM tokens. It opens a *fresh* unit-of-work per poll (session-per-poll
    is mandatory — never hold one transaction open for the whole lifetime) and
    yields the insight each time its status changes, terminating once the row
    reaches a terminal state (COMPLETED / FAILED) or the poll cap is hit.

    On hitting ``max_polls`` without a terminal state it simply returns — the
    row is the source of truth, so the caller can fall back to polling.
    """

    def __init__(
        self,
        factory: InsightWorkUnitFactory,
        *,
        poll_interval_seconds: float = 1.0,
        max_polls: int = 120,
    ) -> None:
        self._factory = factory
        self._poll_interval_seconds = poll_interval_seconds
        self._max_polls = max_polls

    async def _read(self, insight_id: InsightId, user_id: UserId) -> Insight | None:
        async with self._factory() as uow:
            return await uow.insight_repo.get_by_id(insight_id, user_id)

    async def __call__(self, insight_id: InsightId, user_id: UserId) -> AsyncIterator[Insight]:
        insight = await self._read(insight_id, user_id)
        if insight is None:
            raise InsightNotFoundError(str(insight_id))

        yield insight
        last_status = insight.status
        if last_status in _TERMINAL_STATUSES:
            return

        for _ in range(self._max_polls):
            await asyncio.sleep(self._poll_interval_seconds)
            insight = await self._read(insight_id, user_id)
            if insight is None:
                # Row vanished (e.g. deleted mid-stream); treat as not-found end.
                raise InsightNotFoundError(str(insight_id))

            if insight.status != last_status:
                yield insight
                last_status = insight.status
                if last_status in _TERMINAL_STATUSES:
                    return
