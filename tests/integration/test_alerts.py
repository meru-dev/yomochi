import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.factories import login_user, register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")
_PASS = "StrongPass123!"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_alert(
    db_url: str,
    user_id: str,
    *,
    type_: str = "spending_spike",
    subtype: str | None = None,
    title: str = "Test",
    body: str = "body",
    period_year: int = 2026,
    period_month: int = 5,
    is_read: bool = False,
) -> str:
    """Insert a user_alert row directly and return its id."""
    engine = create_async_engine(db_url)
    alert_id = str(uuid.uuid4())
    # Derive a unique subtype from alert_id when not supplied so we never hit
    # the (user_id, subtype, period_year, period_month) unique constraint.
    effective_subtype = subtype if subtype is not None else alert_id
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                """
                INSERT INTO user_alerts
                    (id, user_id, type, subtype, title, body, metadata,
                     period_year, period_month, is_read)
                VALUES
                    (:id, :user_id, :type, :subtype, :title, :body, :metadata,
                     :period_year, :period_month, :is_read)
                """
            ),
            {
                "id": alert_id,
                "user_id": user_id,
                "type": type_,
                "subtype": effective_subtype,
                "title": title,
                "body": body,
                "metadata": "{}",
                "period_year": period_year,
                "period_month": period_month,
                "is_read": is_read,
            },
        )
    await engine.dispose()
    return alert_id


async def _get_user_id(db_url: str, email: str) -> str:
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        row = await conn.execute(sa.text("SELECT id FROM users WHERE email = :e"), {"e": email})
        uid = str(row.scalar_one())
    await engine.dispose()
    return uid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_list_alerts_empty(client: AsyncClient, integration_settings: dict) -> None:
    await register_and_login(client, email="alerts-empty@example.com", password=_PASS)

    resp = await client.get("/api/v1/alerts")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"] == []
    assert data["unread_count"] == 0
    assert data["next_cursor"] is None


async def test_list_alerts_returns_inserted_alert(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "alerts-one@example.com"
    db_url = integration_settings["database_settings"].database_url

    await register_and_login(client, email=email, password=_PASS)
    user_id = await _get_user_id(db_url, email)
    alert_id = await _insert_alert(db_url, user_id, title="Spike alert")

    resp = await client.get("/api/v1/alerts")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == alert_id
    assert data["items"][0]["title"] == "Spike alert"


async def test_list_alerts_unread_count_matches(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "alerts-unread@example.com"
    db_url = integration_settings["database_settings"].database_url

    await register_and_login(client, email=email, password=_PASS)
    user_id = await _get_user_id(db_url, email)
    await _insert_alert(db_url, user_id, is_read=False)
    await _insert_alert(db_url, user_id, is_read=True)

    resp = await client.get("/api/v1/alerts")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["unread_count"] == 1


async def test_unread_count_endpoint(client: AsyncClient, integration_settings: dict) -> None:
    email = "alerts-count@example.com"
    db_url = integration_settings["database_settings"].database_url

    await register_and_login(client, email=email, password=_PASS)
    user_id = await _get_user_id(db_url, email)
    await _insert_alert(db_url, user_id, is_read=False)
    await _insert_alert(db_url, user_id, is_read=False)

    resp = await client.get("/api/v1/alerts/unread-count")

    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 2


async def test_mark_alert_read(client: AsyncClient, integration_settings: dict) -> None:
    email = "alerts-markread@example.com"
    db_url = integration_settings["database_settings"].database_url

    await register_and_login(client, email=email, password=_PASS)
    user_id = await _get_user_id(db_url, email)
    alert_id = await _insert_alert(db_url, user_id, is_read=False)

    patch_resp = await client.patch(f"/api/v1/alerts/{alert_id}/read")
    assert patch_resp.status_code == 204, patch_resp.text

    list_resp = await client.get("/api/v1/alerts")
    assert list_resp.status_code == 200, list_resp.text
    item = list_resp.json()["items"][0]
    assert item["is_read"] is True
    assert list_resp.json()["unread_count"] == 0


async def test_mark_alert_read_wrong_user_returns_404(
    client: AsyncClient, integration_settings: dict
) -> None:
    email_a = "alerts-owner@example.com"
    email_b = "alerts-attacker@example.com"
    db_url = integration_settings["database_settings"].database_url

    # User A creates an alert.
    await register_and_login(client, email=email_a, password=_PASS)
    user_id_a = await _get_user_id(db_url, email_a)
    alert_id = await _insert_alert(db_url, user_id_a)
    await client.post("/api/v1/auth/logout")

    # User B tries to mark it read.
    await register_and_login(client, email=email_b, password=_PASS)
    resp = await client.patch(f"/api/v1/alerts/{alert_id}/read")

    assert resp.status_code == 404, resp.text


async def test_mark_alert_read_nonexistent_returns_404(
    client: AsyncClient, integration_settings: dict
) -> None:
    await register_and_login(client, email="alerts-noexist@example.com", password=_PASS)
    fake_id = str(uuid.uuid4())

    resp = await client.patch(f"/api/v1/alerts/{fake_id}/read")

    assert resp.status_code == 404, resp.text


async def test_clear_alerts(client: AsyncClient, integration_settings: dict) -> None:
    email = "alerts-clear@example.com"
    db_url = integration_settings["database_settings"].database_url

    await register_and_login(client, email=email, password=_PASS)
    user_id = await _get_user_id(db_url, email)
    await _insert_alert(db_url, user_id)
    await _insert_alert(db_url, user_id)

    delete_resp = await client.delete("/api/v1/alerts")
    assert delete_resp.status_code == 204, delete_resp.text

    list_resp = await client.get("/api/v1/alerts")
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json()["items"] == []
    assert list_resp.json()["unread_count"] == 0


async def test_clear_alerts_user_isolation(client: AsyncClient, integration_settings: dict) -> None:
    email_a = "alerts-iso-a@example.com"
    email_b = "alerts-iso-b@example.com"
    db_url = integration_settings["database_settings"].database_url

    # User A inserts 2 alerts.
    await register_and_login(client, email=email_a, password=_PASS)
    user_id_a = await _get_user_id(db_url, email_a)
    await _insert_alert(db_url, user_id_a)
    await _insert_alert(db_url, user_id_a)
    await client.post("/api/v1/auth/logout")

    # User B inserts 1 alert then clears all.
    await register_and_login(client, email=email_b, password=_PASS)
    user_id_b = await _get_user_id(db_url, email_b)
    await _insert_alert(db_url, user_id_b)
    delete_resp = await client.delete("/api/v1/alerts")
    assert delete_resp.status_code == 204, delete_resp.text

    # User B now has 0.
    list_b = await client.get("/api/v1/alerts")
    assert list_b.json()["items"] == []
    await client.post("/api/v1/auth/logout")

    # User A still has 2 (already registered earlier — just log in).
    await login_user(client, email=email_a, password=_PASS)
    list_a = await client.get("/api/v1/alerts")
    assert len(list_a.json()["items"]) == 2


async def test_list_alerts_pagination_cursor(
    client: AsyncClient, integration_settings: dict
) -> None:
    """GET /alerts?limit=2 returns 2 items + cursor; follow-up returns 1 + no cursor."""
    email = "alerts-page@example.com"
    db_url = integration_settings["database_settings"].database_url

    await register_and_login(client, email=email, password=_PASS)
    user_id = await _get_user_id(db_url, email)
    # Insert 3 alerts (each gets unique subtype via uuid default).
    await _insert_alert(db_url, user_id, title="Alert 1")
    await _insert_alert(db_url, user_id, title="Alert 2")
    await _insert_alert(db_url, user_id, title="Alert 3")

    # First page.
    resp1 = await client.get("/api/v1/alerts?limit=2")
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert len(data1["items"]) == 2
    assert data1["next_cursor"] is not None

    # Second page using the cursor.
    cursor = data1["next_cursor"]
    resp2 = await client.get(f"/api/v1/alerts?limit=2&cursor={cursor}")
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert len(data2["items"]) == 1
    assert data2["next_cursor"] is None
