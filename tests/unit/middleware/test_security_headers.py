from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.inbound.http.middleware.security_headers import SecurityHeadersMiddleware


async def _handler(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _make_app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/", _handler),
            Route("/docs", _handler),
            Route("/redoc", _handler),
            Route("/openapi.json", _handler),
        ]
    )
    app.add_middleware(SecurityHeadersMiddleware)
    return app


def test_security_headers_always_present():
    client = TestClient(_make_app())
    resp = client.get("/")
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["X-XSS-Protection"] == "1; mode=block"
    assert "geolocation=()" in resp.headers["Permissions-Policy"]
    assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert resp.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert resp.headers["Cross-Origin-Embedder-Policy"] == "require-corp"


def test_csp_present_on_api_routes():
    client = TestClient(_make_app())
    resp = client.get("/")
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'none'" in csp


def test_csp_absent_on_docs_paths():
    client = TestClient(_make_app())
    for path in ("/docs", "/redoc", "/openapi.json"):
        resp = client.get(path)
        assert "Content-Security-Policy" not in resp.headers, path
        # Other headers should still be set on docs paths.
        assert resp.headers["X-Content-Type-Options"] == "nosniff", path


def test_hsts_absent_over_http():
    client = TestClient(_make_app())
    resp = client.get("/")
    assert "Strict-Transport-Security" not in resp.headers


def test_hsts_present_when_forwarded_https():
    client = TestClient(_make_app())
    resp = client.get("/", headers={"X-Forwarded-Proto": "https"})
    assert "Strict-Transport-Security" in resp.headers
    assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]
    assert "includeSubDomains" in resp.headers["Strict-Transport-Security"]
