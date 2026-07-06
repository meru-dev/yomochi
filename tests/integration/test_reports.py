from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.integration.factories import create_transaction, register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")

_PASS = "StrongPass123!"


async def test_summary_empty_for_period_with_no_transactions(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-empty@example.com", password=_PASS)
    resp = await client.get("/api/v1/reports/summary?year=2026&month=5")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["expenses"] == []
    assert data["income"] == []


async def test_summary_returns_correct_totals_by_type(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-sum@example.com", password=_PASS)
    await create_transaction(
        client, amount="100.00", currency="USD", date="2026-05-01", type_="expense"
    )
    await create_transaction(
        client, amount="50.00", currency="USD", date="2026-05-02", type_="expense"
    )
    await create_transaction(
        client, amount="2000.00", currency="USD", date="2026-05-01", type_="income"
    )

    resp = await client.get("/api/v1/reports/summary?year=2026&month=5")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    usd_expenses = next((e for e in data["expenses"] if e["currency"] == "USD"), None)
    assert usd_expenses is not None
    assert float(usd_expenses["total"]) == pytest.approx(150.0)
    assert usd_expenses["count"] == 2

    usd_income = next((i for i in data["income"] if i["currency"] == "USD"), None)
    assert usd_income is not None
    assert float(usd_income["total"]) == pytest.approx(2000.0)


async def test_summary_multi_currency(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-multi@example.com", password=_PASS)
    await create_transaction(
        client, amount="100.00", currency="USD", date="2026-05-01", type_="expense"
    )
    await create_transaction(
        client, amount="8000", currency="JPY", date="2026-05-01", type_="expense"
    )

    resp = await client.get("/api/v1/reports/summary?year=2026&month=5")
    assert resp.status_code == 200, resp.text
    currencies = {e["currency"] for e in resp.json()["expenses"]}
    assert currencies == {"USD", "JPY"}


async def test_summary_only_counts_transactions_in_period(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-period@example.com", password=_PASS)
    await create_transaction(
        client, amount="100.00", currency="USD", date="2026-05-01", type_="expense"
    )
    await create_transaction(
        client, amount="999.00", currency="USD", date="2026-04-01", type_="expense"
    )

    resp = await client.get("/api/v1/reports/summary?year=2026&month=5")
    assert resp.status_code == 200, resp.text
    usd_expenses = next((e for e in resp.json()["expenses"] if e["currency"] == "USD"), None)
    assert usd_expenses is not None
    assert usd_expenses["count"] == 1


async def test_summary_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/reports/summary?year=2026&month=5")
    assert resp.status_code == 401


async def test_trend_empty_for_user_with_no_transactions(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-trend-empty@example.com", password=_PASS)
    resp = await client.get("/api/v1/reports/trend?currency=USD&months=6")
    assert resp.status_code == 200, resp.text
    assert resp.json()["points"] == []


async def test_trend_returns_monthly_points(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-trend@example.com", password=_PASS)
    await create_transaction(
        client, amount="100.00", currency="USD", date="2026-05-01", type_="expense"
    )
    await create_transaction(
        client, amount="50.00", currency="USD", date="2026-05-15", type_="expense"
    )

    resp = await client.get("/api/v1/reports/trend?currency=USD&months=6")
    assert resp.status_code == 200, resp.text
    points = resp.json()["points"]
    assert len(points) >= 1
    may_point = next((p for p in points if p["month"] == "2026-05"), None)
    assert may_point is not None
    assert float(may_point["total"]) == pytest.approx(150.0)


async def test_trend_only_includes_expenses_not_income(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-trend-type@example.com", password=_PASS)
    await create_transaction(
        client, amount="100.00", currency="USD", date="2026-05-01", type_="expense"
    )
    await create_transaction(
        client, amount="5000.00", currency="USD", date="2026-05-01", type_="income"
    )

    resp = await client.get("/api/v1/reports/trend?currency=USD&months=6")
    assert resp.status_code == 200, resp.text
    may_point = next((p for p in resp.json()["points"] if p["month"] == "2026-05"), None)
    assert may_point is not None
    assert float(may_point["total"]) == pytest.approx(100.0)


async def test_trend_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/reports/trend?currency=USD")
    assert resp.status_code == 401


async def test_trend_week_granularity_returns_iso_year_week_buckets(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-trend-week@example.com", password=_PASS)
    await create_transaction(
        client, amount="42.00", currency="USD", date="2026-05-04", type_="expense"
    )  # ISO week 19, Monday

    resp = await client.get("/api/v1/reports/trend?currency=USD&months=12&granularity=week")
    assert resp.status_code == 200, resp.text
    points = resp.json()["points"]
    # Bucket key shape: "YYYY-Www"
    assert all("-W" in p["month"] for p in points)
    target = next((p for p in points if p["month"] == "2026-W19"), None)
    assert target is not None, points
    assert float(target["total"]) == pytest.approx(42.0)


async def test_trend_invalid_granularity_returns_422(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-trend-bad-gran@example.com", password=_PASS)
    resp = await client.get("/api/v1/reports/trend?currency=USD&months=6&granularity=day")
    assert resp.status_code == 422


async def test_trend_default_granularity_is_month(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-trend-default@example.com", password=_PASS)
    await create_transaction(
        client, amount="10.00", currency="USD", date="2026-05-04", type_="expense"
    )

    resp = await client.get("/api/v1/reports/trend?currency=USD&months=6")
    assert resp.status_code == 200
    points = resp.json()["points"]
    # Month bucket has no "-W" marker
    assert all("-W" not in p["month"] for p in points)


async def test_summary_excludes_future_transactions_in_current_month(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-future-sum@example.com", password=_PASS)
    today = datetime.now(UTC).date()
    tomorrow = today + timedelta(days=1)
    # Past/present transaction in the current month - should be included
    await create_transaction(
        client, amount="100.00", currency="USD", date=today.isoformat(), type_="expense"
    )
    # Future transaction - should be excluded (whether it lands in this month or next)
    await create_transaction(
        client, amount="500.00", currency="USD", date=tomorrow.isoformat(), type_="expense"
    )

    resp = await client.get(f"/api/v1/reports/summary?year={today.year}&month={today.month}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    usd_expenses = next((e for e in data["expenses"] if e["currency"] == "USD"), None)
    assert usd_expenses is not None
    # Should only count the past transaction (100), not the future one (500)
    assert float(usd_expenses["total"]) == pytest.approx(100.0)
    assert usd_expenses["count"] == 1


async def test_trend_excludes_future_transactions(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-future-trend@example.com", password=_PASS)
    today = datetime.now(UTC).date()
    tomorrow = today + timedelta(days=1)
    # Past/present transaction in the current month - should be included
    await create_transaction(
        client, amount="100.00", currency="USD", date=today.isoformat(), type_="expense"
    )
    # Future transaction - should be excluded
    await create_transaction(
        client, amount="500.00", currency="USD", date=tomorrow.isoformat(), type_="expense"
    )

    resp = await client.get("/api/v1/reports/trend?currency=USD&months=6")
    assert resp.status_code == 200, resp.text
    current_month_key = f"{today.year:04d}-{today.month:02d}"
    month_point = next((p for p in resp.json()["points"] if p["month"] == current_month_key), None)
    assert month_point is not None
    # Should only count the past transaction (100), not the future one (500)
    assert float(month_point["total"]) == pytest.approx(100.0)


async def test_summary_includes_all_transactions_in_past_months(client: AsyncClient) -> None:
    await register_and_login(client, email="rep-past-month@example.com", password=_PASS)
    # Transactions in April 2026 (past month)
    await create_transaction(
        client, amount="100.00", currency="USD", date="2026-04-01", type_="expense"
    )
    await create_transaction(
        client, amount="200.00", currency="USD", date="2026-04-30", type_="expense"
    )

    resp = await client.get("/api/v1/reports/summary?year=2026&month=4")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    usd_expenses = next((e for e in data["expenses"] if e["currency"] == "USD"), None)
    assert usd_expenses is not None
    # Should count both transactions in the past month
    assert float(usd_expenses["total"]) == pytest.approx(300.0)
    assert usd_expenses["count"] == 2
