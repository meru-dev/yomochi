import json
from collections.abc import AsyncIterator

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi.responses import StreamingResponse
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel, Field

from app.application.chat.use_cases.chat_stream import (
    ChatQueryCommand,
    ChatStreamDone,
    ChatStreamUseCase,
)
from app.application.common.ai_errors import OpenAICallError
from app.application.common.ports.identity_context import IdentityContext

logger = structlog.get_logger(__name__)

router = ErrorAwareRouter()


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


@router.post("/chat/stream")
@inject
async def stream_chat_message(
    body: ChatStreamRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ChatStreamUseCase],
) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        try:
            async for item in use_case(
                ChatQueryCommand(user_id=identity.user_id, message=body.message)
            ):
                if isinstance(item, str):
                    yield f"data: {json.dumps({'type': 'token', 'content': item})}\n\n"
                elif isinstance(item, ChatStreamDone):
                    yield f"data: {json.dumps({'type': 'done', 'turn_id': item.turn_id, 'context_quality': item.context_quality, 'created_at': item.created_at})}\n\n"
        except OpenAICallError as exc:
            logger.warning(
                "chat_stream_ai_error",
                error=str(exc),
                user_id=str(identity.user_id),
            )
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "message": "AI service temporarily unavailable. Please try again.",
                    }
                )
                + "\n\n"
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
