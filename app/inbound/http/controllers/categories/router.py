from fastapi import APIRouter

from app.inbound.http.controllers.categories.create import router as create_router
from app.inbound.http.controllers.categories.list_ import router as list_router


def make_categories_router() -> APIRouter:
    router = APIRouter(tags=["Categories"])
    router.include_router(list_router, prefix="/categories")
    router.include_router(create_router, prefix="/categories")
    return router
