from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi.responses import Response
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.users.use_cases.change_password import (
    ChangePasswordCommand,
    ChangePasswordUseCase,
)

router = ErrorAwareRouter()


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def change_password(
    body: ChangePasswordRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ChangePasswordUseCase],
) -> Response:
    await use_case(
        ChangePasswordCommand(
            user_id=identity.user_id,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
