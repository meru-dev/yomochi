from datetime import UTC, datetime

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Request, status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.users.audit_event import AuditEvent
from app.application.users.ports.audit_log import AuditLog
from app.application.users.ports.session_store import SessionStore
from app.application.users.ports.token_encoder import TokenEncoder
from app.application.users.session import Session
from app.application.users.use_cases.create_user import CreateUserCommand, CreateUserUseCase
from app.domain.ports.id_generator import SessionIdGenerator
from app.domain.value_objects.enums import AuditEventType
from app.inbound.http.auth.cookie_manager import CookieManager, SessionTtl

router = ErrorAwareRouter()


class RegisterRequest(BaseModel):
    email: str
    password: str


class RegisterResponse(BaseModel):
    user_id: str


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
@inject
async def register(
    request: Request,
    body: RegisterRequest,
    use_case: FromDishka[CreateUserUseCase],
    session_store: FromDishka[SessionStore],
    session_id_gen: FromDishka[SessionIdGenerator],
    audit_log: FromDishka[AuditLog],
    cookie_manager: FromDishka[CookieManager],
    token_encoder: FromDishka[TokenEncoder],
    session_ttl: FromDishka[SessionTtl],
) -> RegisterResponse:
    result = await use_case(CreateUserCommand(email=body.email, raw_password=body.password))
    user_agent = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(UTC)
    session = Session(
        id_=session_id_gen(),
        user_id=result.user_id,
        expires_at=now + session_ttl,
        user_agent=user_agent,
        ip=ip,
    )
    await session_store.save(session)
    await audit_log.record(
        AuditEvent(
            event_type=AuditEventType.USER_REGISTERED,
            user_id=result.user_id,
            occurred_at=now,
            ip=ip,
            user_agent=user_agent,
        )
    )
    cookie_manager.stage_set(token_encoder.encode(session))
    return RegisterResponse(user_id=str(result.user_id))
