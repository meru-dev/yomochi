from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter

from app.application.chat.use_cases.clear_chat_history import (
    ClearChatHistoryCommand,
    ClearChatHistoryUseCase,
)
from app.application.common.ports.identity_context import IdentityContext

router = ErrorAwareRouter()


@router.delete("/chat/history", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def clear_chat_history(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ClearChatHistoryUseCase],
) -> None:
    await use_case(ClearChatHistoryCommand(user_id=identity.user_id))
