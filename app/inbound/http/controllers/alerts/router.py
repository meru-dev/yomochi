# app/inbound/http/controllers/alerts/router.py
from fastapi import APIRouter

from app.inbound.http.controllers.alerts.clear import router as clear_router
from app.inbound.http.controllers.alerts.list_ import router as list_router
from app.inbound.http.controllers.alerts.mark_read import router as mark_read_router
from app.inbound.http.controllers.alerts.unread_count import router as unread_count_router


def make_alerts_router() -> APIRouter:
    router = APIRouter(tags=["Alerts"])
    router.include_router(list_router)
    router.include_router(unread_count_router)
    router.include_router(mark_read_router)
    router.include_router(clear_router)
    return router
