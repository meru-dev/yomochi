from fastapi import APIRouter

from app.inbound.http.controllers.auth.login import router as login_router
from app.inbound.http.controllers.auth.logout import router as logout_router
from app.inbound.http.controllers.auth.password_reset_confirm import (
    router as password_reset_confirm_router,
)
from app.inbound.http.controllers.auth.password_reset_request import (
    router as password_reset_request_router,
)
from app.inbound.http.controllers.auth.register import router as register_router


def make_auth_router() -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["Auth"])
    router.include_router(register_router)
    router.include_router(login_router)
    router.include_router(logout_router)
    router.include_router(password_reset_request_router)
    router.include_router(password_reset_confirm_router)
    return router
