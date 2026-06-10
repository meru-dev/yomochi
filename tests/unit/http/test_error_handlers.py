from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.exceptions.domain_errors import (
    InvalidCursorError,
    InvalidEmailError,
    WeakPasswordError,
)
from app.inbound.http.errors.handlers import _error_body, register_exception_handlers


def test_error_body_structure():
    body = _error_body("auth.required", "Authentication required", request_id="req-123")
    assert body == {
        "error": {
            "code": "auth.required",
            "message": "Authentication required",
            "request_id": "req-123",
        }
    }


def test_error_body_without_request_id():
    body = _error_body("not_found", "Resource not found")
    assert body["error"]["request_id"] is None


def _app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/")
    def _raise() -> None:
        raise exc

    return app


def test_invalid_email_returns_400():
    client = TestClient(_app_raising(InvalidEmailError("bad@")))
    r = client.get("/")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "user.invalid_email"
    assert "Invalid email" in body["error"]["message"]


def test_weak_password_returns_400():
    client = TestClient(_app_raising(WeakPasswordError("too short")))
    r = client.get("/")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "user.weak_password"


def test_invalid_cursor_returns_400():
    client = TestClient(_app_raising(InvalidCursorError("garbage")))
    r = client.get("/")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "pagination.invalid_cursor"


def test_unhandled_exception_returns_500():
    client = TestClient(_app_raising(RuntimeError("boom")), raise_server_exceptions=False)
    r = client.get("/")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "An unexpected error occurred"
