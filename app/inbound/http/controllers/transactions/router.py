from fastapi import APIRouter

from app.inbound.http.controllers.transactions.create import router as create_router
from app.inbound.http.controllers.transactions.delete import router as delete_router
from app.inbound.http.controllers.transactions.get import router as get_router
from app.inbound.http.controllers.transactions.list_ import router as list_router
from app.inbound.http.controllers.transactions.parse_text import router as parse_text_router
from app.inbound.http.controllers.transactions.update import router as update_router


def make_transactions_router() -> APIRouter:
    router = APIRouter(tags=["Transactions"])
    router.include_router(list_router, prefix="/transactions")
    router.include_router(create_router, prefix="/transactions")
    router.include_router(get_router, prefix="/transactions")
    router.include_router(delete_router, prefix="/transactions")
    router.include_router(update_router, prefix="/transactions")
    router.include_router(parse_text_router, prefix="/transactions")
    return router
