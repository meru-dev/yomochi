from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi.responses import Response
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.users.use_cases.confirm_password_reset import (
    ConfirmPasswordResetCommand,
    ConfirmPasswordResetUseCase,
)

router = ErrorAwareRouter()


class PasswordResetConfirmBody(BaseModel):
    token: str
    new_password: str


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def password_reset_confirm(
    body: PasswordResetConfirmBody,
    use_case: FromDishka[ConfirmPasswordResetUseCase],
) -> Response:
    await use_case(ConfirmPasswordResetCommand(token=body.token, new_password=body.new_password))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
