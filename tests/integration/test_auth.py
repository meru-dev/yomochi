import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="module")

_PASS = "StrongPass123!"


async def test_register_returns_201_with_user_id(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@example.com", "password": _PASS},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "user_id" in data
    assert data["user_id"]


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {"email": "dup@example.com", "password": _PASS}
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409, second.text


async def test_register_weak_password_returns_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "abc"},
    )
    assert resp.status_code == 400, resp.text


async def test_register_invalid_email_returns_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": _PASS},
    )
    assert resp.status_code == 400, resp.text


async def test_login_returns_200_and_session_usable(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": "login@example.com", "password": _PASS}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": _PASS}
    )
    assert resp.status_code == 200, resp.text
    assert "user_id" in resp.json()
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": "wrongpass@example.com", "password": _PASS}
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "WrongPassword99!"},
    )
    assert resp.status_code == 401, resp.text


async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": _PASS},
    )
    assert resp.status_code == 401, resp.text


async def test_logout_returns_204_and_revokes_session(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": "logout@example.com", "password": _PASS}
    )
    await client.post("/api/v1/auth/login", json={"email": "logout@example.com", "password": _PASS})
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 204, resp.text
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 401


async def test_unauthenticated_protected_endpoint_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_password_reset_request_returns_202(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": "reset@example.com", "password": _PASS}
    )
    resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "reset@example.com"},
    )
    assert resp.status_code == 202, resp.text


async def test_password_reset_request_unknown_email_still_returns_202(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "ghost@example.com"},
    )
    assert resp.status_code == 202, resp.text
