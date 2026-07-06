import pytest
from httpx import AsyncClient

from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_create_recurring_rule_returns_201(client: AsyncClient) -> None:
    await register_and_login(client)

    resp = await client.post(
        "/api/v1/recurring-rules",
        json={
            "amount": "5000.00",
            "currency": "USD",
            "type": "income",
            "recurrence": "monthly",
            "day_of_month": 1,
            "start_date": "2026-06-01",
            "merchant": "Employer",
        },
    )

    assert resp.status_code == 201, resp.text
    assert "id" in resp.json()


async def test_create_weekly_rule_requires_day_of_week(client: AsyncClient) -> None:
    await register_and_login(client)

    resp = await client.post(
        "/api/v1/recurring-rules",
        json={
            "amount": "50.00",
            "currency": "USD",
            "type": "expense",
            "recurrence": "weekly",
            "start_date": "2026-06-01",
        },
    )

    assert resp.status_code == 422, resp.text


async def test_list_recurring_rules(client: AsyncClient) -> None:
    await register_and_login(client)
    await client.post(
        "/api/v1/recurring-rules",
        json={
            "amount": "100.00",
            "currency": "EUR",
            "type": "expense",
            "recurrence": "monthly",
            "day_of_month": 15,
            "start_date": "2026-06-01",
            "merchant": "Gym",
        },
    )

    resp = await client.get("/api/v1/recurring-rules")

    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1


async def test_pause_rule(client: AsyncClient) -> None:
    await register_and_login(client)
    create = await client.post(
        "/api/v1/recurring-rules",
        json={
            "amount": "1000.00",
            "currency": "USD",
            "type": "income",
            "recurrence": "monthly",
            "day_of_month": 1,
            "start_date": "2026-06-01",
        },
    )
    rule_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/recurring-rules/{rule_id}",
        json={"status": "paused"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paused"


async def test_delete_rule_returns_204(client: AsyncClient) -> None:
    await register_and_login(client)
    create_rule = await client.post(
        "/api/v1/recurring-rules",
        json={
            "amount": "30.00",
            "currency": "USD",
            "type": "expense",
            "recurrence": "monthly",
            "day_of_month": 1,
            "start_date": "2026-05-01",
            "merchant": "Netflix",
        },
    )
    rule_id = create_rule.json()["id"]

    del_resp = await client.delete(f"/api/v1/recurring-rules/{rule_id}")
    assert del_resp.status_code == 204


async def test_cross_user_isolation(client: AsyncClient) -> None:
    await register_and_login(client, email="recurring_a@test.com")
    create = await client.post(
        "/api/v1/recurring-rules",
        json={
            "amount": "500.00",
            "currency": "USD",
            "type": "income",
            "recurrence": "monthly",
            "day_of_month": 1,
            "start_date": "2026-06-01",
        },
    )
    rule_id = create.json()["id"]

    await register_and_login(client, email="recurring_b@test.com")
    resp = await client.get(f"/api/v1/recurring-rules/{rule_id}")
    assert resp.status_code == 404
