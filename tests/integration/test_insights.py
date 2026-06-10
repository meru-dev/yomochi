import pytest
from httpx import AsyncClient

from tests.integration.factories import create_transaction, register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")

_PASS = "StrongPass123!"
_PERIOD = {"period": "monthly", "period_year": 2026, "period_month": 5}


async def test_request_insight_insufficient_transactions_returns_422(client: AsyncClient) -> None:
    await register_and_login(client, email="ins-few@example.com", password=_PASS)
    for i in range(2):
        await create_transaction(client, date=f"2026-05-0{i + 1}")

    resp = await client.post("/api/v1/insights/requests", json=_PERIOD)
    assert resp.status_code == 422, resp.text


async def test_request_insight_returns_202_with_id(client: AsyncClient) -> None:
    await register_and_login(client, email="ins-ok@example.com", password=_PASS)
    for i in range(5):
        await create_transaction(client, date=f"2026-05-{i + 1:02d}")

    resp = await client.post("/api/v1/insights/requests", json=_PERIOD)
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert "id" in data
    assert data["id"]


async def test_list_insights_empty_for_new_user(client: AsyncClient) -> None:
    await register_and_login(client, email="ins-list@example.com", password=_PASS)
    resp = await client.get("/api/v1/insights")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"] == []
    assert data["next_cursor"] is None


async def test_list_insights_contains_requested_insight(client: AsyncClient) -> None:
    await register_and_login(client, email="ins-list2@example.com", password=_PASS)
    for i in range(5):
        await create_transaction(client, date=f"2026-05-{i + 1:02d}")

    await client.post("/api/v1/insights/requests", json=_PERIOD)

    resp = await client.get("/api/v1/insights")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1


async def test_get_insight_returns_200(client: AsyncClient) -> None:
    await register_and_login(client, email="ins-get@example.com", password=_PASS)
    for i in range(5):
        await create_transaction(client, date=f"2026-05-{i + 1:02d}")

    request_resp = await client.post("/api/v1/insights/requests", json=_PERIOD)
    insight_id = request_resp.json()["id"]

    resp = await client.get(f"/api/v1/insights/{insight_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == insight_id
    assert data["status"] in ("pending", "queued", "processing", "completed", "failed")


async def test_get_insight_other_user_returns_404(client: AsyncClient) -> None:
    await register_and_login(client, email="ins-owner@example.com", password=_PASS)
    for i in range(5):
        await create_transaction(client, date=f"2026-05-{i + 1:02d}")
    request_resp = await client.post("/api/v1/insights/requests", json=_PERIOD)
    insight_id = request_resp.json()["id"]
    await client.post("/api/v1/auth/logout")

    await register_and_login(client, email="ins-attacker@example.com", password=_PASS)
    resp = await client.get(f"/api/v1/insights/{insight_id}")
    assert resp.status_code == 404, resp.text


async def test_list_insights_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/insights")
    assert resp.status_code == 401


async def test_get_insight_response_includes_budget_summary_field(client: AsyncClient) -> None:
    """Schema-level contract: budget_summary field is always present (null for non-completed)."""
    await register_and_login(client, email="ins-budget@example.com", password=_PASS)
    for i in range(5):
        await create_transaction(client, date=f"2026-05-{i + 1:02d}")
    request_resp = await client.post("/api/v1/insights/requests", json=_PERIOD)
    insight_id = request_resp.json()["id"]

    resp = await client.get(f"/api/v1/insights/{insight_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "budget_summary" in data
    # Worker has not run in this test → budget_summary is null
    assert data["budget_summary"] is None
