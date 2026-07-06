"""Seed a demo persona directly via DB (no running server required).

Requires DATABASE_URL env var. Dates are always current: the loader shifts
fixture dates so the newest transaction lands on today, keeping only the
last 90 days.
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import bcrypt

from tests.fixtures.personas.loader import _WINDOW_DAYS, PERSONAS, load_fixture


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _next_monthly_fire(day: int) -> date:
    today = date.today()
    try:
        candidate = today.replace(day=day)
        if candidate > today:
            return candidate
    except ValueError:
        pass
    year, month = today.year, today.month + 1
    if month > 12:
        year, month = year + 1, 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _to_asyncpg_dsn(db_url: str) -> str:
    return db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "asyncpg://", "postgresql://"
    )


async def seed(persona: str) -> None:
    import asyncpg

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL not set.")

    fixture = load_fixture(persona)
    email: str = fixture["user"]["email"]
    password: str = fixture["user"]["password"]
    shifted_txs: list[dict[str, Any]] = fixture["transactions"]
    raw_recurring: list[dict[str, Any]] = fixture.get("recurring", [])

    today = date.today()
    cutoff = today - timedelta(days=_WINDOW_DAYS)

    if not shifted_txs:
        sys.exit(f"No transactions fall within last {_WINDOW_DAYS} days. Check fixture.")

    print(f"Seeding persona '{persona}'...")
    print(f"  User:         {email}")
    print(f"  Date range:   {cutoff} -> {today}")
    print(f"  Transactions: {len(shifted_txs)}")

    password_hash = _hash_password(password)
    now = datetime.now(UTC)
    user_id = uuid4()

    tx_rows = [
        (
            uuid4(),
            user_id,
            Decimal(tx["amount"]),
            tx["currency"],
            date.fromisoformat(tx["date"]),
            tx["type"].lower(),
            tx.get("merchant"),
            tx.get("notes"),
            _uuid(tx.get("category_id")),
            now,
        )
        for tx in shifted_txs
    ]

    rule_rows = []
    for rule in raw_recurring:
        day = rule.get("day_of_month")
        rec = rule.get("recurrence", "monthly")
        next_fire = (
            _next_monthly_fire(day) if rec == "monthly" and day else today + timedelta(days=1)
        )
        rule_rows.append(
            (
                uuid4(),
                user_id,
                Decimal(rule["amount"]),
                rule["currency"],
                rule["type"].lower(),
                rule.get("merchant"),
                rule.get("notes"),
                _uuid(rule.get("category_id")),
                rec,
                day,  # day_of_month
                None,  # day_of_week
                None,  # month
                date.fromisoformat(rule["start_date"]),  # already shifted by loader
                None,  # end_date
                "active",
                next_fire,
                now,
            )
        )

    conn = await asyncpg.connect(_to_asyncpg_dsn(db_url))
    try:
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
        if existing:
            sys.exit(
                f"\nUser '{email}' already exists.\n"
                "Run with --reset first to remove existing demo data."
            )

        async with conn.transaction():
            await conn.execute(
                "INSERT INTO users (id, email, password_hash, plan, created_at) "
                "VALUES ($1, $2, $3, $4, $5)",
                user_id,
                email,
                password_hash,
                "free",
                now,
            )
            await conn.executemany(
                "INSERT INTO transactions "
                "(id, user_id, amount_value, currency_code, date, type, merchant, notes, "
                "category_id, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                tx_rows,
            )
            if rule_rows:
                await conn.executemany(
                    "INSERT INTO recurring_rules "
                    "(id, user_id, amount_value, currency_code, type, merchant, notes, "
                    "category_id, recurrence, day_of_month, day_of_week, month, "
                    "start_date, end_date, status, next_fire_date, created_at) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
                    "$13, $14, $15, $16, $17)",
                    rule_rows,
                )

            # Trigger the insight-worker end-to-end for the CURRENT month, the same
            # way the HTTP RequestInsight use case does: an `insights` row in QUEUED
            # status + an `InsightRequested` outbox event. The outbox-worker relays it
            # to Kafka, the insight-worker claims it (QUEUED → PROCESSING) and runs the
            # deterministic pipeline over the 4 months just seeded.
            #
            # Behavioral-shift ALERTS need no seed record: the scheduler's
            # `detect_shift_alerts_job` scans recently-active users on its own (daily
            # 02:00 UTC) and writes alerts idempotently from these same aggregates.
            insight_id = uuid4()
            insight_payload = {
                "insight_id": str(insight_id),
                "user_id": str(user_id),
                "period": "monthly",
                "period_year": today.year,
                "period_month": today.month,
            }
            await conn.execute(
                "INSERT INTO insights "
                "(id, user_id, period, period_year, period_month, status, created_at) "
                "VALUES ($1, $2, 'monthly', $3, $4, 'queued', $5)",
                insight_id,
                user_id,
                today.year,
                today.month,
                now,
            )
            await conn.execute(
                "INSERT INTO outbox_events "
                "(id, event_type, aggregate_id, payload, status, occurred_at, user_id) "
                "VALUES ($1, 'InsightRequested', $2, $3::jsonb, 'PENDING', $4, $5)",
                uuid4(),
                str(insight_id),
                json.dumps(insight_payload),
                now,
                user_id,
            )
    finally:
        await conn.close()

    print(f"  Recurring rules:  {len(rule_rows)} created.")
    print(f"  Insight queued:   {today.year}-{today.month:02d} (InsightRequested → outbox)")
    print(f"\nDone. Persona '{persona}' is ready.")
    print(f"  Email:    {email}")
    print(f"  Password: {password}")


async def _reset(persona: str) -> None:
    import asyncpg

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit(
            "DATABASE_URL not set.\n"
            "Export it or run: DATABASE_URL=postgresql://... make seed-demo-reset"
        )

    fixture = load_fixture(persona)
    email: str = fixture["user"]["email"]

    print(f"Resetting persona '{persona}' (email={email})...")
    conn = await asyncpg.connect(_to_asyncpg_dsn(db_url))
    try:
        deleted = await conn.fetchval("DELETE FROM users WHERE email = $1 RETURNING id", email)
        if deleted:
            print(f"  Deleted user '{email}' and all associated data (cascade).")
        else:
            print(f"  No user found with email '{email}' — nothing to delete.")
    finally:
        await conn.close()
    print("Done. You can now run `make seed-demo` again.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or reset demo personas in Yomochi via DB.")
    parser.add_argument(
        "--persona",
        default="meiko_tokyo",
        choices=PERSONAS,
        help="Which persona to seed (default: meiko_tokyo)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the demo user and all their data (requires DATABASE_URL)",
    )
    args = parser.parse_args()

    if args.reset:
        asyncio.run(_reset(args.persona))
    else:
        asyncio.run(seed(args.persona))


if __name__ == "__main__":
    main()
