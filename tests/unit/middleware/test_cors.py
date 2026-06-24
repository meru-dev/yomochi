from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.main.config.settings import AppSettings


async def _handler(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _make_app(cors_allow_origins: str = "") -> Starlette:
    """Build a minimal Starlette app with CORSMiddleware wired the same way
    app_factory does: guard on cors_allow_origin_list, outermost placement."""
    cfg = AppSettings(cors_allow_origins=cors_allow_origins, _env_file=None)
    app = Starlette(routes=[Route("/", _handler)])
    if cfg.cors_allow_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cfg.cors_allow_origin_list),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    return app


# ---------------------------------------------------------------------------
# cors_allow_origin_list property
# ---------------------------------------------------------------------------


def test_origin_list_empty_by_default() -> None:
    cfg = AppSettings(_env_file=None)
    assert cfg.cors_allow_origin_list == ()


def test_origin_list_single() -> None:
    cfg = AppSettings(cors_allow_origins="https://app.example.com", _env_file=None)
    assert cfg.cors_allow_origin_list == ("https://app.example.com",)


def test_origin_list_multiple_with_spaces() -> None:
    cfg = AppSettings(
        cors_allow_origins=" https://app.example.com , http://localhost:3000 ",
        _env_file=None,
    )
    assert cfg.cors_allow_origin_list == ("https://app.example.com", "http://localhost:3000")


# ---------------------------------------------------------------------------
# CORS disabled (empty config) — no allow-origin header on any request
# ---------------------------------------------------------------------------


def test_cors_disabled_by_default_no_header() -> None:
    client = TestClient(_make_app())
    resp = client.get("/", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers


def test_cors_disabled_preflight_gets_no_header() -> None:
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.options(
        "/",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in resp.headers


# ---------------------------------------------------------------------------
# CORS enabled — allowed origin
# ---------------------------------------------------------------------------

_ALLOWED_ORIGIN = "https://app.example.com"


def test_cors_preflight_allowed_origin_echoed() -> None:
    client = TestClient(_make_app(cors_allow_origins=_ALLOWED_ORIGIN))
    resp = client.options(
        "/",
        headers={
            "Origin": _ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN


def test_cors_preflight_credentials_header_present() -> None:
    client = TestClient(_make_app(cors_allow_origins=_ALLOWED_ORIGIN))
    resp = client.options(
        "/",
        headers={
            "Origin": _ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_simple_request_allowed_origin_echoed() -> None:
    client = TestClient(_make_app(cors_allow_origins=_ALLOWED_ORIGIN))
    resp = client.get("/", headers={"Origin": _ALLOWED_ORIGIN})
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN


# ---------------------------------------------------------------------------
# CORS enabled — disallowed origin is not reflected
# ---------------------------------------------------------------------------


def test_cors_disallowed_origin_no_allow_header() -> None:
    client = TestClient(_make_app(cors_allow_origins=_ALLOWED_ORIGIN))
    resp = client.get("/", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers


def test_cors_preflight_disallowed_origin_no_allow_header() -> None:
    client = TestClient(
        _make_app(cors_allow_origins=_ALLOWED_ORIGIN), raise_server_exceptions=False
    )
    resp = client.options(
        "/",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in resp.headers


# ---------------------------------------------------------------------------
# Multiple allowed origins
# ---------------------------------------------------------------------------


def test_cors_multiple_origins_each_echoed() -> None:
    origins = "https://app.example.com,http://localhost:3000"
    for origin in ("https://app.example.com", "http://localhost:3000"):
        client = TestClient(_make_app(cors_allow_origins=origins))
        resp = client.get("/", headers={"Origin": origin})
        assert resp.headers.get("access-control-allow-origin") == origin, origin
