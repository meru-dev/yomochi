from fastapi import APIRouter

from app.inbound.http.controllers.recurring.create import router as create_router
from app.inbound.http.controllers.recurring.delete import router as delete_router
from app.inbound.http.controllers.recurring.get import router as get_router
from app.inbound.http.controllers.recurring.list_ import router as list_router
from app.inbound.http.controllers.recurring.update import router as update_router


def make_recurring_router() -> APIRouter:
    router = APIRouter(tags=["Recurring Rules"])
    router.include_router(list_router, prefix="/recurring-rules")
    router.include_router(create_router, prefix="/recurring-rules")
    router.include_router(get_router, prefix="/recurring-rules")
    router.include_router(update_router, prefix="/recurring-rules")
    router.include_router(delete_router, prefix="/recurring-rules")
    return router
