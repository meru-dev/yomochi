from fastapi import APIRouter

from app.inbound.http.controllers.insights.get import router as get_router
from app.inbound.http.controllers.insights.list_ import router as list_router
from app.inbound.http.controllers.insights.request import router as request_router


def make_insights_router() -> APIRouter:
    router = APIRouter(tags=["Insights"])
    router.include_router(request_router, prefix="/insights")
    router.include_router(list_router, prefix="/insights")
    router.include_router(get_router, prefix="/insights")
    return router
