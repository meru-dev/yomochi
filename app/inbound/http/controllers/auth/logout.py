from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi.responses import Response
from fastapi_error_map import ErrorAwareRouter

from app.application.common.ports.identity_context import IdentityContext
from app.application.users.use_cases.logout import LogoutCommand, LogoutUseCase
from app.inbound.http.auth.cookie_manager import CookieManager

router = ErrorAwareRouter()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def logout(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[LogoutUseCase],
    cookie_manager: FromDishka[CookieManager],
) -> Response:
    await use_case(LogoutCommand(session_id=identity.session_id, user_id=identity.user_id))
    cookie_manager.stage_delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
