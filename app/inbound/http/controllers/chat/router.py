from fastapi import APIRouter

from app.inbound.http.controllers.chat.clear import router as clear_router
from app.inbound.http.controllers.chat.history import router as history_router
from app.inbound.http.controllers.chat.send import router as send_router
from app.inbound.http.controllers.chat.stream import router as stream_router


def make_chat_router() -> APIRouter:
    router = APIRouter(tags=["Chat"])
    router.include_router(send_router)
    router.include_router(history_router)
    router.include_router(clear_router)
    router.include_router(stream_router)
    return router
