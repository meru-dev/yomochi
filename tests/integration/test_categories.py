import pytest
from httpx import AsyncClient

from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_list_categories_returns_system_categories(client: AsyncClient) -> None:
    await register_and_login(client)

    resp = await client.get("/api/v1/categories")

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    system = [c for c in items if c["is_system"]]
    assert len(system) == 48  # 13 groups + 35 leaves
    names = {c["name"] for c in system}
    assert "Food & Drink" in names
    assert "Transport" in names


async def test_list_categories_includes_parent_id_and_type(client: AsyncClient) -> None:
    await register_and_login(client)

    resp = await client.get("/api/v1/categories")
    items = resp.json()["items"]

    groups = [c for c in items if c["is_system"] and c["parent_id"] is None]
    leaves = [c for c in items if c["is_system"] and c["parent_id"] is not None]
    assert len(groups) == 13
    assert len(leaves) == 35
    for c in items:
        assert "type" in c
        assert c["type"] in ("income", "expense")


async def test_list_categories_system_first(client: AsyncClient) -> None:
    await register_and_login(client)

    await client.post(
        "/api/v1/categories",
        json={"name": "AAA user group", "type": "expense"},
    )

    resp = await client.get("/api/v1/categories")
    items = resp.json()["items"]

    saw_user = False
    for item in items:
        if not item["is_system"]:
            saw_user = True
        if saw_user and item["is_system"]:
            pytest.fail("System category appeared after user-owned category")


async def test_create_group_category_returns_201(client: AsyncClient) -> None:
    await register_and_login(client)

    resp = await client.post(
        "/api/v1/categories",
        json={"name": "My hobbies", "type": "expense", "icon": "🎯", "color": "#FF0000"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "id" in body


async def test_create_leaf_under_group(client: AsyncClient) -> None:
    await register_and_login(client)

    group_resp = await client.post(
        "/api/v1/categories",
        json={"name": "My sports", "type": "expense"},
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    leaf_resp = await client.post(
        "/api/v1/categories",
        json={"name": "Gym membership", "type": "expense", "parent_id": group_id},
    )
    assert leaf_resp.status_code == 201, leaf_resp.text

    list_resp = await client.get("/api/v1/categories")
    items = list_resp.json()["items"]
    leaf = next((c for c in items if c["name"] == "Gym membership"), None)
    assert leaf is not None
    assert leaf["parent_id"] == group_id
    assert leaf["type"] == "expense"


async def test_create_category_with_unknown_parent_returns_404(client: AsyncClient) -> None:
    await register_and_login(client)

    resp = await client.post(
        "/api/v1/categories",
        json={
            "name": "Orphan",
            "type": "expense",
            "parent_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert resp.status_code == 404, resp.text


async def test_create_leaf_under_leaf_returns_422(client: AsyncClient) -> None:
    await register_and_login(client)

    group_resp = await client.post(
        "/api/v1/categories",
        json={"name": "My travel", "type": "expense"},
    )
    group_id = group_resp.json()["id"]

    leaf_resp = await client.post(
        "/api/v1/categories",
        json={"name": "Flights", "type": "expense", "parent_id": group_id},
    )
    leaf_id = leaf_resp.json()["id"]

    resp = await client.post(
        "/api/v1/categories",
        json={"name": "Business class", "type": "expense", "parent_id": leaf_id},
    )
    assert resp.status_code == 422, resp.text


async def test_create_leaf_type_mismatch_returns_422(client: AsyncClient) -> None:
    await register_and_login(client)

    group_resp = await client.post(
        "/api/v1/categories",
        json={"name": "My income group", "type": "income"},
    )
    group_id = group_resp.json()["id"]

    resp = await client.post(
        "/api/v1/categories",
        json={"name": "Wrong type leaf", "type": "expense", "parent_id": group_id},
    )
    assert resp.status_code == 422, resp.text


async def test_create_duplicate_name_returns_409(client: AsyncClient) -> None:
    await register_and_login(client)

    await client.post("/api/v1/categories", json={"name": "Yoga group", "type": "expense"})
    resp = await client.post("/api/v1/categories", json={"name": "Yoga group", "type": "expense"})

    assert resp.status_code == 409, resp.text


async def test_same_name_allowed_for_different_users(client: AsyncClient) -> None:
    await register_and_login(client, email="cat_user_a@example.com")
    body = {"name": "My hobbies group", "type": "expense"}
    resp_a = await client.post("/api/v1/categories", json=body)
    assert resp_a.status_code == 201
    await client.post("/api/v1/auth/logout")

    await register_and_login(client, email="cat_user_b@example.com")
    resp_b = await client.post("/api/v1/categories", json=body)
    assert resp_b.status_code == 201

    list_resp = await client.get("/api/v1/categories")
    user_cats = [c for c in list_resp.json()["items"] if not c["is_system"]]
    assert len(user_cats) == 1
    assert user_cats[0]["name"] == "My hobbies group"


async def test_unauthenticated_access_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/categories")
    assert resp.status_code == 401

    resp = await client.post("/api/v1/categories", json={"name": "X", "type": "expense"})
    assert resp.status_code == 401
