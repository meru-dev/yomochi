from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.chat.use_cases.list_chat_history import (
    ListChatHistoryQuery,
    ListChatHistoryUseCase,
)
from app.application.common.ports.identity_context import IdentityContext

router = ErrorAwareRouter()


class ChatTurnResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ListChatHistoryResponse(BaseModel):
    items: list[ChatTurnResponse]
    next_cursor: str | None


@router.get("/chat/history", status_code=status.HTTP_200_OK, response_model=ListChatHistoryResponse)
@inject
async def list_chat_history(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ListChatHistoryUseCase],
    limit: int = 20,
    cursor: str | None = None,
) -> ListChatHistoryResponse:
    result = await use_case(
        ListChatHistoryQuery(user_id=identity.user_id, limit=limit, cursor=cursor)
    )
    return ListChatHistoryResponse(
        items=[
            ChatTurnResponse(
                id=str(t.id),
                role=t.role,
                content=t.content,
                created_at=t.created_at.isoformat(),
            )
            for t in result.turns
        ],
        next_cursor=result.next_cursor,
    )
