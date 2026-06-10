from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi.responses import Response
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.users.use_cases.start_password_reset import (
    StartPasswordResetCommand,
    StartPasswordResetUseCase,
)

router = ErrorAwareRouter()


class PasswordResetRequestBody(BaseModel):
    email: str


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
@inject
async def password_reset_request(
    body: PasswordResetRequestBody,
    use_case: FromDishka[StartPasswordResetUseCase],
) -> Response:
    await use_case(StartPasswordResetCommand(email=body.email))
    return Response(status_code=status.HTTP_202_ACCEPTED)
