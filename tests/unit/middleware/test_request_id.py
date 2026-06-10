from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.inbound.http.middleware.request_id import RequestIdMiddleware


async def _handler(request: Request) -> JSONResponse:
    return JSONResponse({"request_id": request.state.request_id})


def _make_app():
    app = Starlette(routes=[Route("/", _handler)])
    app.add_middleware(RequestIdMiddleware)
    return app


def test_request_id_generated_when_not_provided():
    client = TestClient(_make_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 0
    assert resp.json()["request_id"] == resp.headers["X-Request-ID"]


def test_request_id_echoed_when_provided():
    client = TestClient(_make_app())
    resp = client.get("/", headers={"X-Request-ID": "my-custom-id"})
    assert resp.headers["X-Request-ID"] == "my-custom-id"
    assert resp.json()["request_id"] == "my-custom-id"
