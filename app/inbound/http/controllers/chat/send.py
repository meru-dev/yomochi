from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel, Field

from app.application.chat.use_cases.chat_query import ChatQueryCommand, ChatQueryUseCase
from app.application.common.ports.identity_context import IdentityContext

router = ErrorAwareRouter()


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class ChatMessageResponse(BaseModel):
    turn_id: str
    answer: str
    context_quality: str
    created_at: str


@router.post(
    "/chat",
    status_code=status.HTTP_200_OK,
    response_model=ChatMessageResponse,
)
@inject
async def send_chat_message(
    body: ChatMessageRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ChatQueryUseCase],
) -> ChatMessageResponse:
    result = await use_case(ChatQueryCommand(user_id=identity.user_id, message=body.message))
    return ChatMessageResponse(
        turn_id=str(result.turn_id),
        answer=result.answer,
        context_quality=result.context_quality.value,
        created_at=result.created_at.isoformat(),
    )
