from fastapi import APIRouter

from app.inbound.http.controllers.ingestion.parse_receipt import router as parse_receipt_router


def make_ingestion_router() -> APIRouter:
    router = APIRouter(tags=["Ingestion"])
    router.include_router(parse_receipt_router)
    return router
