from httpx import AsyncClient


async def register_user(
    client: AsyncClient,
    email: str = "user@example.com",
    password: str = "StrongPass123!",
) -> None:
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, f"register_user failed [{resp.status_code}]: {resp.text}"


async def login_user(
    client: AsyncClient,
    email: str = "user@example.com",
    password: str = "StrongPass123!",
) -> None:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"login_user failed [{resp.status_code}]: {resp.text}"


async def register_and_login(
    client: AsyncClient,
    email: str = "user@example.com",
    password: str = "StrongPass123!",
) -> AsyncClient:
    """Register + login with one call. Returns the same client (cookie already set)."""
    await register_user(client, email, password)
    await login_user(client, email, password)
    return client


async def create_transaction(
    client: AsyncClient,
    *,
    amount: str = "10.00",
    currency: str = "USD",
    date: str = "2026-05-01",
    type_: str = "expense",
    merchant: str | None = None,
) -> str:
    """Create a transaction for the currently logged-in user. Returns transaction ID."""
    payload: dict = {"amount": amount, "currency": currency, "date": date, "type": type_}
    if merchant is not None:
        payload["merchant"] = merchant
    resp = await client.post("/api/v1/transactions", json=payload)
    assert resp.status_code == 201, f"create_transaction failed [{resp.status_code}]: {resp.text}"
    return resp.json()["id"]


async def create_category(
    client: AsyncClient,
    *,
    name: str = "Food",
    color: str = "#FF5733",
) -> str:
    """Create a category for the currently logged-in user. Returns category ID."""
    resp = await client.post("/api/v1/categories", json={"name": name, "color": color})
    assert resp.status_code == 201, f"create_category failed [{resp.status_code}]: {resp.text}"
    return resp.json()["id"]
