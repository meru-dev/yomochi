import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main.api.app_factory import make_app
from app.main.config.settings import (
    AppSettings,
    AuthSettings,
    DatabaseSettings,
    ObservabilitySettings,
    RedisSettings,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest.fixture(scope="module")
def smoke_settings(postgres_url: str, redis_url: str) -> dict:
    return {
        "app_settings": AppSettings(debug=True, rate_limit_enabled=False),
        "database_settings": DatabaseSettings(database_url=postgres_url, db_use_null_pool=True),
        "redis_settings": RedisSettings(redis_url=redis_url),
        "auth_settings": AuthSettings(
            jwt_secret="smoke-test-secret-must-be-at-least-32b", cookie_secure=False
        ),
        "observability_settings": ObservabilitySettings(log_format="console", otel_enabled=False),
    }


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def smoke_client(
    smoke_settings: dict,
    run_migrations: None,
):
    app = make_app(**smoke_settings)
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as client,
    ):
        yield client


async def test_register_login_me_logout(smoke_client: AsyncClient) -> None:
    email = "smoke@example.com"
    password = "StrongPass123!"

    resp = await smoke_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text
    assert "user_id" in resp.json()

    resp = await smoke_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    assert "user_id" in resp.json()
    assert "auth" in resp.cookies

    resp = await smoke_client.get("/api/v1/users/me")
    assert resp.status_code == 200, resp.text
    me = resp.json()
    assert me["email"] == email
    assert me["plan"] == "free"

    resp = await smoke_client.get("/api/v1/users/me/sessions")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) >= 1

    resp = await smoke_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204, resp.text

    resp = await smoke_client.get("/api/v1/users/me")
    assert resp.status_code == 401, resp.text


async def test_duplicate_register_returns_409(smoke_client: AsyncClient) -> None:
    email = "duplicate@example.com"
    password = "StrongPass123!"

    resp = await smoke_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201

    resp = await smoke_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "user.already_exists"


async def test_password_reset_flow(smoke_client: AsyncClient) -> None:
    email = "reset@example.com"
    password = "OldPass123!"

    await smoke_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )

    resp = await smoke_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": email},
    )
    assert resp.status_code == 202

    resp = await smoke_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 202

    resp = await smoke_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "invalid-token", "new_password": "NewPass123!"},
    )
    assert resp.status_code == 400
