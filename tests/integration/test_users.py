import pytest
from httpx import AsyncClient

from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")

_PASS = "StrongPass123!"


async def test_get_me_returns_user_data(client: AsyncClient) -> None:
    await register_and_login(client, email="me@example.com", password=_PASS)
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["email"] == "me@example.com"
    assert "id" in data
    assert "plan" in data


async def test_get_me_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_change_password_returns_204(client: AsyncClient) -> None:
    await register_and_login(client, email="chpass@example.com", password=_PASS)
    resp = await client.put(
        "/api/v1/users/me/password",
        json={"current_password": _PASS, "new_password": "NewStrongPass456!"},
    )
    assert resp.status_code == 204, resp.text

    await client.post("/api/v1/auth/logout")
    login_old = await client.post(
        "/api/v1/auth/login",
        json={"email": "chpass@example.com", "password": _PASS},
    )
    assert login_old.status_code == 401

    login_new = await client.post(
        "/api/v1/auth/login",
        json={"email": "chpass@example.com", "password": "NewStrongPass456!"},
    )
    assert login_new.status_code == 200


async def test_change_password_wrong_current_returns_400(client: AsyncClient) -> None:
    await register_and_login(client, email="wrongcur@example.com", password=_PASS)
    resp = await client.put(
        "/api/v1/users/me/password",
        json={"current_password": "WrongCurrent99!", "new_password": "NewStrongPass456!"},
    )
    assert resp.status_code == 400, resp.text  # InvalidCurrentPasswordError → 400


async def test_list_sessions_returns_current_session(client: AsyncClient) -> None:
    await register_and_login(client, email="sessions@example.com", password=_PASS)
    resp = await client.get("/api/v1/users/me/sessions")
    assert resp.status_code == 200, resp.text
    sessions = resp.json()
    assert isinstance(sessions, list)
    assert len(sessions) >= 1
    assert "id" in sessions[0]
    assert "expires_at" in sessions[0]


async def test_list_sessions_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me/sessions")
    assert resp.status_code == 401


async def test_list_audit_events_returns_events_after_login(client: AsyncClient) -> None:
    await register_and_login(client, email="audit@example.com", password=_PASS)
    resp = await client.get("/api/v1/users/audit-events")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "events" in data
    assert isinstance(data["events"], list)
    assert len(data["events"]) >= 1
    event_types = [e["event_type"] for e in data["events"]]
    # AuditEventType enum values: "user_login", "user_registered"
    assert any(et in ("user_login", "user_registered") for et in event_types)


async def test_list_audit_events_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/audit-events")
    assert resp.status_code == 401
