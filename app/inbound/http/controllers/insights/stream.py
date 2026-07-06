import json
from collections.abc import AsyncIterator
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi.responses import StreamingResponse
from fastapi_error_map import ErrorAwareRouter

from app.application.common.ports.identity_context import IdentityContext
from app.application.insights.use_cases.get_insight import (
    GetInsightQuery,
    GetInsightUseCase,
    InsightNotFoundError,
)
from app.application.insights.use_cases.stream_insight import StreamInsightUseCase
from app.domain.value_objects.enums import InsightStatus
from app.domain.value_objects.ids import InsightId
from app.inbound.http.controllers.insights.get import _serialize

router = ErrorAwareRouter()


@router.get(
    "/{insight_id}/stream",
    error_map={InsightNotFoundError: status.HTTP_404_NOT_FOUND},
)
@inject
async def stream_insight(
    insight_id: UUID,
    identity: FromDishka[IdentityContext],
    get_use_case: FromDishka[GetInsightUseCase],
    stream_use_case: FromDishka[StreamInsightUseCase],
) -> StreamingResponse:
    iid = InsightId(insight_id)
    user_id = identity.user_id

    # Surface a clean 404 BEFORE the streaming body starts. Once the
    # StreamingResponse generator runs, error_map can no longer set the status.
    await get_use_case(GetInsightQuery(insight_id=iid, user_id=user_id))

    async def generate() -> AsyncIterator[str]:
        saw_terminal = False
        async for insight in stream_use_case(iid, user_id):
            if insight.status == InsightStatus.COMPLETED:
                saw_terminal = True
                payload = _serialize(insight).model_dump()
                payload["type"] = "completed"
                yield f"data: {json.dumps(payload)}\n\n"
            elif insight.status == InsightStatus.FAILED:
                saw_terminal = True
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "status": "failed",
                            "error_message": insight.error_message,
                        }
                    )
                    + "\n\n"
                )
            else:
                yield f"data: {json.dumps({'type': 'status', 'status': insight.status.value})}\n\n"

        if not saw_terminal:
            yield f"data: {json.dumps({'type': 'timeout'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
