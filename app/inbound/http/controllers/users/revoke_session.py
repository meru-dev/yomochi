from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi.responses import Response
from fastapi_error_map import ErrorAwareRouter

from app.application.common.ports.identity_context import IdentityContext
from app.application.users.use_cases.logout import LogoutCommand, LogoutUseCase
from app.domain.value_objects.ids import SessionId

router = ErrorAwareRouter()


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def revoke_session(
    session_id: UUID,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[LogoutUseCase],
) -> Response:
    target_session_id = SessionId(session_id)
    await use_case(LogoutCommand(session_id=target_session_id, user_id=identity.user_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
