from fastapi import APIRouter

from app.inbound.http.controllers.reports.summary import router as summary_router
from app.inbound.http.controllers.reports.trend import router as trend_router


def make_reports_router() -> APIRouter:
    router = APIRouter(prefix="/reports", tags=["Reports"])
    router.include_router(summary_router)
    router.include_router(trend_router)
    return router
