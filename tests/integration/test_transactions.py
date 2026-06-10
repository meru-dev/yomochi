import pytest
from httpx import AsyncClient

from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_create_transaction_returns_201(client: AsyncClient) -> None:
    await register_and_login(client)

    resp = await client.post(
        "/api/v1/transactions",
        json={
            "amount": "12.50",
            "currency": "USD",
            "date": "2026-05-01",
            "type": "expense",
            "merchant": "Coffee Shop",
        },
    )

    assert resp.status_code == 201, resp.text
    assert "id" in resp.json()


async def test_create_transaction_invalid_currency_returns_422(client: AsyncClient) -> None:
    await register_and_login(client)

    resp = await client.post(
        "/api/v1/transactions",
        json={"amount": "10.00", "currency": "XXX", "date": "2026-05-01", "type": "expense"},
    )

    assert resp.status_code == 400, resp.text


async def test_get_transaction_returns_200(client: AsyncClient) -> None:
    await register_and_login(client)

    create = await client.post(
        "/api/v1/transactions",
        json={"amount": "50.00", "currency": "EUR", "date": "2026-05-01", "type": "income"},
    )
    tx_id = create.json()["id"]

    resp = await client.get(f"/api/v1/transactions/{tx_id}")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == tx_id
    assert data["amount"] == "50.0000"
    assert data["currency"] == "EUR"
    assert data["type"] == "income"


async def test_get_other_users_transaction_returns_404(client: AsyncClient) -> None:
    """Cross-user isolation: GET /{id} must return 404, not 403."""
    await register_and_login(client, email="owner@example.com")
    create = await client.post(
        "/api/v1/transactions",
        json={"amount": "10.00", "currency": "USD", "date": "2026-05-01", "type": "expense"},
    )
    tx_id = create.json()["id"]
    await client.post("/api/v1/auth/logout")

    await register_and_login(client, email="attacker@example.com")
    resp = await client.get(f"/api/v1/transactions/{tx_id}")

    assert resp.status_code == 404, resp.text


async def test_list_transactions_cursor_pagination(client: AsyncClient) -> None:
    await register_and_login(client)

    # Create 5 transactions on different dates
    for i in range(1, 6):
        await client.post(
            "/api/v1/transactions",
            json={"amount": "10.00", "currency": "JPY", "date": f"2026-05-0{i}", "type": "expense"},
        )

    page1 = await client.get("/api/v1/transactions?limit=2")
    assert page1.status_code == 200
    data1 = page1.json()
    assert len(data1["items"]) == 2
    assert data1["next_cursor"] is not None

    page2 = await client.get(f"/api/v1/transactions?limit=2&cursor={data1['next_cursor']}")
    assert page2.status_code == 200
    data2 = page2.json()
    assert len(data2["items"]) == 2
    assert data2["next_cursor"] is not None

    ids1 = {tx["id"] for tx in data1["items"]}
    ids2 = {tx["id"] for tx in data2["items"]}
    assert ids1.isdisjoint(ids2)


async def test_list_transactions_last_page_has_no_cursor(client: AsyncClient) -> None:
    await register_and_login(client)

    for i in range(1, 4):
        await client.post(
            "/api/v1/transactions",
            json={"amount": "1.00", "currency": "USD", "date": f"2026-05-0{i}", "type": "expense"},
        )

    resp = await client.get("/api/v1/transactions?limit=10")
    assert resp.status_code == 200
    assert resp.json()["next_cursor"] is None


async def test_update_transaction_returns_204(client: AsyncClient) -> None:
    await register_and_login(client)

    create = await client.post(
        "/api/v1/transactions",
        json={"amount": "10.00", "currency": "USD", "date": "2026-05-01", "type": "expense"},
    )
    tx_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/transactions/{tx_id}",
        json={"merchant": "Updated merchant"},
    )
    assert resp.status_code == 204, resp.text

    get = await client.get(f"/api/v1/transactions/{tx_id}")
    assert get.json()["merchant"] == "Updated merchant"
    assert get.json()["updated_at"] is not None


async def test_update_other_users_transaction_returns_404(client: AsyncClient) -> None:
    await register_and_login(client, email="owner2@example.com")
    create = await client.post(
        "/api/v1/transactions",
        json={"amount": "5.00", "currency": "USD", "date": "2026-05-01", "type": "expense"},
    )
    tx_id = create.json()["id"]
    await client.post("/api/v1/auth/logout")

    await register_and_login(client, email="attacker2@example.com")
    resp = await client.patch(
        f"/api/v1/transactions/{tx_id}",
        json={"merchant": "hacked"},
    )
    assert resp.status_code == 404, resp.text


async def test_delete_transaction_returns_204(client: AsyncClient) -> None:
    await register_and_login(client)

    create = await client.post(
        "/api/v1/transactions",
        json={"amount": "10.00", "currency": "USD", "date": "2026-05-01", "type": "expense"},
    )
    tx_id = create.json()["id"]

    resp = await client.delete(f"/api/v1/transactions/{tx_id}")
    assert resp.status_code == 204, resp.text

    get = await client.get(f"/api/v1/transactions/{tx_id}")
    assert get.status_code == 404


async def test_multi_currency_list_no_conversion(client: AsyncClient) -> None:
    """Multi-currency transactions are returned as-is, never summed or converted."""
    await register_and_login(client)

    await client.post(
        "/api/v1/transactions",
        json={"amount": "100.00", "currency": "USD", "date": "2026-05-01", "type": "expense"},
    )
    await client.post(
        "/api/v1/transactions",
        json={"amount": "8000", "currency": "JPY", "date": "2026-05-02", "type": "expense"},
    )

    resp = await client.get("/api/v1/transactions")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    currencies = {tx["currency"] for tx in items}
    assert currencies == {"USD", "JPY"}
