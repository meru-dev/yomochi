import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")

_PASS = "StrongPass123!"


async def _get_user_id(db_url: str, email: str) -> str:
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
        uid = str(result.scalar_one())
    await engine.dispose()
    return uid


async def _insert_turn(
    db_url: str,
    user_id: str,
    *,
    role: str = "user",
    content: str = "test message",
) -> str:
    engine = create_async_engine(db_url)
    turn_id = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("""
                INSERT INTO chat_turns (id, user_id, role, content, chunks_used)
                VALUES (:id, :uid, :role, :content, '[]'::jsonb)
            """),
            {"id": turn_id, "uid": user_id, "role": role, "content": content},
        )
    await engine.dispose()
    return turn_id


# ── GET /api/v1/chat/history ──────────────────────────────────────────────────


async def test_chat_history_empty_for_new_user(client: AsyncClient) -> None:
    await register_and_login(client, email="chat-hist-empty@example.com", password=_PASS)
    resp = await client.get("/api/v1/chat/history")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"] == []
    assert data["next_cursor"] is None


async def test_chat_history_returns_inserted_turns(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "chat-hist-one@example.com"
    await register_and_login(client, email=email, password=_PASS)
    db_url = integration_settings["database_settings"].database_url
    uid = await _get_user_id(db_url, email)
    await _insert_turn(db_url, uid, role="user", content="Hello?")
    await _insert_turn(db_url, uid, role="assistant", content="Hi!")

    resp = await client.get("/api/v1/chat/history")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2


async def test_chat_history_user_isolation(client: AsyncClient, integration_settings: dict) -> None:
    email_a = "chat-iso-a@example.com"
    email_b = "chat-iso-b@example.com"
    await register_and_login(client, email=email_a, password=_PASS)
    db_url = integration_settings["database_settings"].database_url
    uid_a = await _get_user_id(db_url, email_a)
    await _insert_turn(db_url, uid_a, content="User A message")

    await register_and_login(client, email=email_b, password=_PASS)
    resp = await client.get("/api/v1/chat/history")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ── DELETE /api/v1/chat/history ───────────────────────────────────────────────


async def test_clear_chat_history_returns_204(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "chat-clear@example.com"
    await register_and_login(client, email=email, password=_PASS)
    db_url = integration_settings["database_settings"].database_url
    uid = await _get_user_id(db_url, email)
    await _insert_turn(db_url, uid, content="to be deleted")

    resp = await client.delete("/api/v1/chat/history")
    assert resp.status_code == 204, resp.text

    list_resp = await client.get("/api/v1/chat/history")
    assert list_resp.json()["items"] == []


async def test_clear_chat_history_idempotent(client: AsyncClient) -> None:
    await register_and_login(client, email="chat-clear-idem@example.com", password=_PASS)
    resp = await client.delete("/api/v1/chat/history")
    assert resp.status_code == 204, resp.text


# ── POST /api/v1/chat — input validation only (no OpenAI) ────────────────────


async def test_chat_send_validates_empty_message(client: AsyncClient) -> None:
    await register_and_login(client, email="chat-val@example.com", password=_PASS)
    resp = await client.post("/api/v1/chat", json={"message": ""})
    assert resp.status_code == 422, resp.text


async def test_chat_send_requires_auth(client: AsyncClient) -> None:
    # client fixture has a fresh cookie jar — no auth cookie set.
    resp = await client.post("/api/v1/chat", json={"message": "hello"})
    assert resp.status_code in (401, 403), resp.text
