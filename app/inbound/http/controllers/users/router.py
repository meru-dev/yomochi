from fastapi import APIRouter

from app.inbound.http.controllers.users.audit import router as audit_router
from app.inbound.http.controllers.users.change_password import router as change_password_router
from app.inbound.http.controllers.users.me import router as me_router
from app.inbound.http.controllers.users.revoke_session import router as revoke_session_router
from app.inbound.http.controllers.users.sessions import router as sessions_router


def make_users_router() -> APIRouter:
    router = APIRouter(prefix="/users", tags=["Users"])
    router.include_router(me_router)
    router.include_router(change_password_router)
    router.include_router(sessions_router)
    router.include_router(revoke_session_router)
    router.include_router(audit_router)
    return router
