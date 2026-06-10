from fastapi import APIRouter

from app.inbound.http.controllers.alerts.router import make_alerts_router
from app.inbound.http.controllers.auth.router import make_auth_router
from app.inbound.http.controllers.categories.router import make_categories_router
from app.inbound.http.controllers.chat.router import make_chat_router
from app.inbound.http.controllers.ingestion.router import make_ingestion_router
from app.inbound.http.controllers.insights.router import make_insights_router
from app.inbound.http.controllers.recurring.router import make_recurring_router
from app.inbound.http.controllers.reports.router import make_reports_router
from app.inbound.http.controllers.search import make_search_router
from app.inbound.http.controllers.transactions.router import make_transactions_router
from app.inbound.http.controllers.users.router import make_users_router


def make_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(make_auth_router())
    router.include_router(make_users_router())
    router.include_router(make_transactions_router())
    router.include_router(make_categories_router())
    router.include_router(make_insights_router())
    router.include_router(make_search_router())
    router.include_router(make_reports_router())
    router.include_router(make_recurring_router())
    router.include_router(make_alerts_router())
    router.include_router(make_chat_router())
    router.include_router(make_ingestion_router())
    return router
