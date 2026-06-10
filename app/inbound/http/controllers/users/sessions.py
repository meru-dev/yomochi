from datetime import datetime

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.common.ports.identity_context import IdentityContext
from app.application.users.ports.session_store import SessionStore

router = ErrorAwareRouter()


class SessionResponse(BaseModel):
    id: str
    user_agent: str
    ip: str
    expires_at: datetime


@router.get("/me/sessions", status_code=status.HTTP_200_OK, response_model=list[SessionResponse])
@inject
async def list_sessions(
    identity: FromDishka[IdentityContext],
    session_store: FromDishka[SessionStore],
) -> list[SessionResponse]:
    sessions = await session_store.list_active(identity.user_id)
    return [
        SessionResponse(
            id=str(s.id_),
            user_agent=s.user_agent,
            ip=s.ip,
            expires_at=s.expires_at,
        )
        for s in sessions
    ]
