"""Integration tests for SqlaChatToolsReader.

Covers:
- search_transactions: pg_trgm ILIKE match on merchant/notes, user-scope isolation.
- get_spend_window: date-range correctness (only transactions in window are included).
- get_month_summary: smoke test against live Postgres.
- get_category_trend: series returns only matching category.
- get_user_profile: returns non-empty result when transactions exist.
- tools-mode session lifecycle: the reader opens a FRESH SHORT session per tool
  call and releases its connection before returning, so a sequence of tool calls
  does not pin connections (ARCHITECTURE §10.4 / bug B14 invariant).

Uses testcontainers Postgres (pgvector/pgvector:pg16 image which includes pg_trgm).
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.outbound.adapters.sqla.chat.chat_tools_reader import SqlaChatToolsReader
from app.outbound.adapters.system.clock import SystemClock
from tests.integration.factories import (
    create_transaction,
    register_and_login,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


# ---------------------------------------------------------------------------
# Session-scoped engine for direct SQLA access (bypasses HTTP layer)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def direct_engine(integration_settings: dict):  # type: ignore[no-untyped-def]
    db_url = integration_settings["database_settings"].database_url
    engine = create_async_engine(db_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


def _reader(engine: AsyncEngine) -> SqlaChatToolsReader:
    """Build a reader from a session factory over the given engine.

    Mirrors the APP-scoped DI wiring: the reader is handed an
    ``async_sessionmaker`` and opens its own short session per tool call.
    """
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, autoflush=False, expire_on_commit=False
    )
    return SqlaChatToolsReader(session_factory=factory, clock=SystemClock())


# ---------------------------------------------------------------------------
# search_transactions — ILIKE + user isolation
# ---------------------------------------------------------------------------


async def test_search_transactions_finds_merchant_match(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    await register_and_login(client, email="search1@example.com")

    # Create transactions: one that matches, one that does not
    await create_transaction(client, merchant="Starbucks Coffee", amount="5.00")
    await create_transaction(client, merchant="ACME Corp", amount="10.00")

    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200, me.text
    user_id = me.json()["id"]

    result = await _reader(direct_engine).search_transactions(user_id, "star", 10)

    assert result.query == "star"
    merchants = [m.merchant for m in result.matches]
    assert any("Starbucks" in (m or "") for m in merchants), f"Expected Starbucks in {merchants}"
    assert not any("ACME" in (m or "") for m in merchants), f"ACME should not appear: {merchants}"


async def test_search_transactions_user_isolation(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    """User A's transactions must NOT appear in User B's search results."""
    # User A
    await register_and_login(client, email="isolation_a@example.com")
    await create_transaction(client, merchant="SecretMerchant", amount="99.00")
    await client.post("/api/v1/auth/logout")

    # User B
    await register_and_login(client, email="isolation_b@example.com")
    await create_transaction(client, merchant="PublicStore", amount="1.00")
    me_b = await client.get("/api/v1/users/me")
    user_b_id = me_b.json()["id"]

    result = await _reader(direct_engine).search_transactions(user_b_id, "SecretMerchant", 10)

    assert result.matches == [], (
        f"User B should not see User A's 'SecretMerchant': {result.matches}"
    )


async def test_search_transactions_notes_match(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    await register_and_login(client, email="notes_search@example.com")

    resp = await client.post(
        "/api/v1/transactions",
        json={
            "amount": "15.00",
            "currency": "USD",
            "date": "2026-05-01",
            "type": "expense",
            "notes": "reimbursable_lunch_note_xyz",
        },
    )
    assert resp.status_code == 201, resp.text

    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    result = await _reader(direct_engine).search_transactions(
        user_id, "reimbursable_lunch_note_xyz", 10
    )

    assert len(result.matches) == 1
    assert "reimbursable_lunch_note_xyz" in (result.matches[0].notes or "")


# ---------------------------------------------------------------------------
# get_spend_window — date-range correctness
# ---------------------------------------------------------------------------


async def test_get_spend_window_includes_only_range(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    await register_and_login(client, email="window@example.com")

    # Two transactions inside the window
    await create_transaction(
        client, amount="100.00", currency="USD", date="2026-04-15", type_="expense"
    )
    await create_transaction(
        client, amount="50.00", currency="USD", date="2026-04-30", type_="expense"
    )
    # One transaction outside the window (2026-05-01)
    await create_transaction(
        client, amount="999.00", currency="USD", date="2026-05-01", type_="expense"
    )

    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    result = await _reader(direct_engine).get_spend_window(
        user_id,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )

    assert result.start_date == date(2026, 4, 1)
    assert result.end_date == date(2026, 4, 30)
    assert len(result.by_currency) == 1
    usd = result.by_currency[0]
    assert usd.currency == "USD"
    # Total expenses in window = 100 + 50 = 150; the 999 outside window must not appear
    assert usd.total_expenses == Decimal("150"), f"Expected 150 but got {usd.total_expenses}"


async def test_get_spend_window_empty_range_returns_empty(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    await register_and_login(client, email="window_empty@example.com")

    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    result = await _reader(direct_engine).get_spend_window(
        user_id,
        start_date=date(2020, 1, 1),
        end_date=date(2020, 1, 31),
    )

    assert result.by_currency == []


# ---------------------------------------------------------------------------
# get_month_summary — smoke test
# ---------------------------------------------------------------------------


async def test_get_month_summary_smoke(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    await register_and_login(client, email="monthsummary@example.com")

    await create_transaction(
        client, amount="500.00", currency="USD", date="2026-05-10", type_="income"
    )
    await create_transaction(
        client, amount="100.00", currency="USD", date="2026-05-15", type_="expense"
    )

    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    result = await _reader(direct_engine).get_month_summary(user_id, 2026, 5)

    assert result.year == 2026
    assert result.month == 5
    assert len(result.by_currency) == 1
    usd = result.by_currency[0]
    assert usd.total_income == Decimal("500")
    assert usd.total_expenses == Decimal("100")


# ---------------------------------------------------------------------------
# get_category_trend — only target category appears
# ---------------------------------------------------------------------------


async def test_get_category_trend_returns_matching_category(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    await register_and_login(client, email="trend@example.com")

    # Create a parent group first, then leaf categories under it (top-level = group, can't assign)
    parent_resp = await client.post(
        "/api/v1/categories", json={"name": "TrendGroup", "type": "expense"}
    )
    assert parent_resp.status_code == 201, parent_resp.text
    parent_id = parent_resp.json()["id"]

    cat_resp = await client.post(
        "/api/v1/categories",
        json={"name": "TrendCat", "color": "#123456", "type": "expense", "parent_id": parent_id},
    )
    assert cat_resp.status_code == 201, cat_resp.text
    cat_id = cat_resp.json()["id"]

    cat2_resp = await client.post(
        "/api/v1/categories",
        json={"name": "OtherCat", "color": "#654321", "type": "expense", "parent_id": parent_id},
    )
    assert cat2_resp.status_code == 201, cat2_resp.text
    cat2_id = cat2_resp.json()["id"]

    # Use a date 1 month ago so it always falls within the n_months=6 window.
    today = datetime.now(UTC).date()
    if today.month == 1:
        trend_date = today.replace(year=today.year - 1, month=12, day=15)
    else:
        trend_date = today.replace(month=today.month - 1, day=15)
    trend_date_str = trend_date.isoformat()
    trend_date_str2 = trend_date.replace(day=16).isoformat()

    tx1_resp = await client.post(
        "/api/v1/transactions",
        json={
            "amount": "75.00",
            "currency": "USD",
            "date": trend_date_str,
            "type": "expense",
            "category_id": cat_id,
        },
    )
    assert tx1_resp.status_code == 201, tx1_resp.text

    # Different category — must NOT inflate TrendCat
    tx2_resp = await client.post(
        "/api/v1/transactions",
        json={
            "amount": "200.00",
            "currency": "USD",
            "date": trend_date_str2,
            "type": "expense",
            "category_id": cat2_id,
        },
    )
    assert tx2_resp.status_code == 201, tx2_resp.text

    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    result = await _reader(direct_engine).get_category_trend(user_id, "TrendCat", 6)

    assert result.category == "TrendCat"
    expected_month = trend_date.month
    expected_year = trend_date.year
    trend_pts = [p for p in result.series if p.month == expected_month and p.year == expected_year]
    assert len(trend_pts) == 1, (
        f"Expected 1 point for {expected_year}-{expected_month:02d}, got {result.series}"
    )
    assert trend_pts[0].amount == Decimal("75")


# ---------------------------------------------------------------------------
# get_user_profile — basic smoke
# ---------------------------------------------------------------------------


async def test_get_user_profile_returns_non_empty_for_recent_data(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    await register_and_login(client, email="profile@example.com")

    # Use a date 1 month ago so it always falls inside the 4-month rolling window.
    today = datetime.now(UTC).date()
    # Step back one month (simple arithmetic — avoids dateutil dependency)
    if today.month == 1:
        recent_date = today.replace(year=today.year - 1, month=12)
    else:
        recent_date = today.replace(month=today.month - 1)
    recent_date_str = recent_date.isoformat()

    await create_transaction(
        client, amount="300.00", currency="USD", date=recent_date_str, type_="expense"
    )

    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    result = await _reader(direct_engine).get_user_profile(user_id)

    assert result.months_covered == 4
    assert len(result.by_currency) >= 1
    usd = next(s for s in result.by_currency if s.currency == "USD")
    assert usd.total_expenses >= Decimal("300")


# ---------------------------------------------------------------------------
# Session lifecycle — per-call short sessions, no connection held across calls
# (ARCHITECTURE §10.4 / bug B14 invariant for the tools-mode chat path)
# ---------------------------------------------------------------------------


async def test_tools_reader_does_not_pin_connection_across_calls(
    client: AsyncClient, integration_settings: dict, run_migrations: None
) -> None:
    """A sequence of tool calls must succeed against a pool of exactly ONE
    connection with no overflow.

    If the reader held a connection open across calls (the B14 regression), the
    second checkout would block until ``pool_timeout`` and then raise
    ``TimeoutError``. Because each public method opens and CLOSES its own short
    session, the single pooled connection is released between calls and every
    call in the sequence succeeds.
    """
    await register_and_login(client, email="pool_lifecycle@example.com")
    await create_transaction(
        client, merchant="LifecycleCafe", amount="42.00", currency="USD", type_="expense"
    )
    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    # Deliberately tiny pool: 1 connection, no overflow, short timeout. A reader
    # that pinned a connection across calls would block then time out here.
    db_url = integration_settings["database_settings"].database_url
    tiny_engine = create_async_engine(db_url, pool_size=1, max_overflow=0, pool_timeout=5)
    try:
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            tiny_engine, autoflush=False, expire_on_commit=False
        )
        reader = SqlaChatToolsReader(session_factory=factory, clock=SystemClock())

        # Several sequential tool calls exercising every public method. Each must
        # release the single connection before the next can check it out.
        today = datetime.now(UTC).date()
        await reader.get_user_profile(user_id)
        await reader.get_month_summary(user_id, today.year, today.month)
        await reader.get_spend_window(user_id, start_date=date(today.year, 1, 1), end_date=today)
        await reader.get_category_trend(user_id, "Groceries", 3)
        search = await reader.search_transactions(user_id, "Lifecycle", 10)

        # Sanity: the last call actually returned data, proving the connections
        # were live (not silently degraded), and the merchant we wrote is found.
        assert any("Lifecycle" in (m.merchant or "") for m in search.matches)

        # The pool only ever has one connection; if any call had leaked it, the
        # checkedout count would be > 0 here. After the sequence it must be 0.
        assert tiny_engine.pool.checkedout() == 0  # type: ignore[attr-defined]
    finally:
        await tiny_engine.dispose()


# ---------------------------------------------------------------------------
# list_categories — distinct user categories with counts (Task 2)
# ---------------------------------------------------------------------------


async def test_list_categories_returns_user_categories_with_counts(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    """list_categories must return distinct category names with correct transaction counts.

    Three transactions across two categories; result ordered by count desc.
    """
    await register_and_login(client, email="listcat_user@example.com")

    # Create a parent group (not assignable directly in this system)
    parent_resp = await client.post(
        "/api/v1/categories", json={"name": "ListCatGroup", "type": "expense"}
    )
    assert parent_resp.status_code == 201, parent_resp.text
    parent_id = parent_resp.json()["id"]

    # Two leaf categories under the group
    cat_a_resp = await client.post(
        "/api/v1/categories",
        json={
            "name": "Groceries LC",
            "color": "#aaaaaa",
            "type": "expense",
            "parent_id": parent_id,
        },
    )
    assert cat_a_resp.status_code == 201, cat_a_resp.text
    cat_a_id = cat_a_resp.json()["id"]

    cat_b_resp = await client.post(
        "/api/v1/categories",
        json={
            "name": "Transport LC",
            "color": "#bbbbbb",
            "type": "expense",
            "parent_id": parent_id,
        },
    )
    assert cat_b_resp.status_code == 201, cat_b_resp.text
    cat_b_id = cat_b_resp.json()["id"]

    # 2 transactions in Groceries LC, 1 in Transport LC
    for day in (1, 2):
        resp = await client.post(
            "/api/v1/transactions",
            json={
                "amount": "20.00",
                "currency": "USD",
                "date": f"2026-05-{day:02d}",
                "type": "expense",
                "category_id": cat_a_id,
            },
        )
        assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/v1/transactions",
        json={
            "amount": "15.00",
            "currency": "USD",
            "date": "2026-05-03",
            "type": "expense",
            "category_id": cat_b_id,
        },
    )
    assert resp.status_code == 201, resp.text

    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    result = await _reader(direct_engine).list_categories(user_id)

    names = [c.name for c in result.categories]
    assert "Groceries LC" in names, f"Expected Groceries LC in {names}"
    assert "Transport LC" in names, f"Expected Transport LC in {names}"

    by_name = {c.name: c for c in result.categories}
    assert by_name["Groceries LC"].transaction_count == 2
    assert by_name["Transport LC"].transaction_count == 1

    # Ordered by count desc — Groceries LC (2) must come before Transport LC (1)
    assert names.index("Groceries LC") < names.index("Transport LC"), (
        f"Expected Groceries LC before Transport LC, got: {names}"
    )

    # All returned categories must have a type set
    for cat in result.categories:
        assert cat.category_type in ("expense", "income"), f"Unexpected type: {cat.category_type}"


async def test_list_categories_user_isolation(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    """list_categories must never leak another user's categories.

    User A has SecretCatA with a transaction. User B has OwnCatB with a
    transaction. Querying as User B must return OwnCatB and must NOT return
    SecretCatA. This test would fail if the reader's user_id filter were removed.
    """
    # User A — registers, creates a private category + transaction
    await register_and_login(client, email="listcat_isola@example.com")

    parent_a_resp = await client.post(
        "/api/v1/categories", json={"name": "SecretGroup", "type": "expense"}
    )
    assert parent_a_resp.status_code == 201, parent_a_resp.text
    parent_a_id = parent_a_resp.json()["id"]

    secret_resp = await client.post(
        "/api/v1/categories",
        json={
            "name": "SecretCatA",
            "color": "#cccccc",
            "type": "expense",
            "parent_id": parent_a_id,
        },
    )
    assert secret_resp.status_code == 201, secret_resp.text
    secret_id = secret_resp.json()["id"]

    tx_a = await client.post(
        "/api/v1/transactions",
        json={
            "amount": "5.00",
            "currency": "USD",
            "date": "2026-05-01",
            "type": "expense",
            "category_id": secret_id,
        },
    )
    assert tx_a.status_code == 201, tx_a.text
    await client.post("/api/v1/auth/logout")

    # User B — registers, creates their own category + transaction
    await register_and_login(client, email="listcat_isolb@example.com")

    parent_b_resp = await client.post(
        "/api/v1/categories", json={"name": "OwnGroup", "type": "expense"}
    )
    assert parent_b_resp.status_code == 201, parent_b_resp.text
    parent_b_id = parent_b_resp.json()["id"]

    own_resp = await client.post(
        "/api/v1/categories",
        json={
            "name": "OwnCatB",
            "color": "#dddddd",
            "type": "expense",
            "parent_id": parent_b_id,
        },
    )
    assert own_resp.status_code == 201, own_resp.text
    own_id = own_resp.json()["id"]

    tx_b = await client.post(
        "/api/v1/transactions",
        json={
            "amount": "7.00",
            "currency": "USD",
            "date": "2026-05-02",
            "type": "expense",
            "category_id": own_id,
        },
    )
    assert tx_b.status_code == 201, tx_b.text

    me_b = await client.get("/api/v1/users/me")
    user_b_id = me_b.json()["id"]

    result = await _reader(direct_engine).list_categories(user_b_id)
    names = [c.name for c in result.categories]

    # User B's own category must appear
    assert "OwnCatB" in names, f"User B's own category must be present: {names}"
    # User A's secret category must never leak
    assert "SecretCatA" not in names, f"User B must not see User A's category: {names}"


async def test_list_categories_skips_uncategorised_transactions(
    client: AsyncClient, direct_engine: AsyncEngine, run_migrations: None
) -> None:
    """Transactions with no category_id must not produce a null-name entry."""
    await register_and_login(client, email="listcat_nocat@example.com")

    # Transaction with no category
    await client.post(
        "/api/v1/transactions",
        json={"amount": "50.00", "currency": "USD", "date": "2026-05-10", "type": "expense"},
    )

    me = await client.get("/api/v1/users/me")
    user_id = me.json()["id"]

    result = await _reader(direct_engine).list_categories(user_id)
    for cat in result.categories:
        assert cat.name is not None, "Null category name must not appear in results"
