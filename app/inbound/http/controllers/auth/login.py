from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Request, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.users.ports.token_encoder import TokenEncoder
from app.application.users.use_cases.login import LoginCommand, LoginUseCase
from app.inbound.http.auth.cookie_manager import CookieManager

router = ErrorAwareRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    user_id: str


@router.post("/login", status_code=status.HTTP_200_OK, response_model=LoginResponse)
@inject
async def login(
    request: Request,
    body: LoginRequest,
    use_case: FromDishka[LoginUseCase],
    cookie_manager: FromDishka[CookieManager],
    token_encoder: FromDishka[TokenEncoder],
) -> LoginResponse:
    user_agent = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else "unknown"
    result = await use_case(
        LoginCommand(
            email=body.email,
            raw_password=body.password,
            user_agent=user_agent,
            ip=ip,
        )
    )
    cookie_manager.stage_set(token_encoder.encode(result.session))
    return LoginResponse(user_id=str(result.session.user_id))
