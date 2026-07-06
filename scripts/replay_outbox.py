"""Replay quarantined (FAILED) outbox rows back to PENDING (F17).

A broker outage longer than ``max_retries × poll_interval`` quarantines outbox
rows as FAILED, where they are otherwise stranded forever. This admin tool flips
selected FAILED rows back to PENDING (retry_count reset) so the outbox-worker
picks them up on its next poll.

Requires DATABASE_URL. Refuses to act without an explicit selector. Examples:

    # See what would be replayed (no writes)
    DATABASE_URL=... uv run python -m scripts.replay_outbox --all --dry-run

    # Replay everything that failed at least 10 min ago (downstream recovered)
    DATABASE_URL=... uv run python -m scripts.replay_outbox --all --min-age-minutes 10

    # Replay one event type, capped
    DATABASE_URL=... uv run python -m scripts.replay_outbox --event-type InsightRequested --limit 50

    # Replay specific rows
    DATABASE_URL=... uv run python -m scripts.replay_outbox --id <uuid> --id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.outbound.adapters.sqla.common.outbox_admin import SqlaOutboxAdmin


async def _run(args: argparse.Namespace) -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL not set.")

    failed_before = (
        datetime.now(UTC) - timedelta(minutes=args.min_age_minutes)
        if args.min_age_minutes
        else None
    )
    ids = [UUID(x) for x in args.id] or None

    engine = create_async_engine(db_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            admin = SqlaOutboxAdmin(session)
            affected = await admin.requeue_failed(
                ids=ids,
                event_type=args.event_type,
                failed_before=failed_before,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            if args.dry_run:
                print(f"[dry-run] {len(affected)} FAILED row(s) would be requeued:")
            else:
                await session.commit()
                print(f"Requeued {len(affected)} FAILED row(s) → PENDING:")
            for row_id in affected:
                print(f"  {row_id}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay FAILED outbox rows back to PENDING (F17).")
    parser.add_argument(
        "--id", action="append", default=[], help="Requeue a specific row id (repeatable)."
    )
    parser.add_argument("--event-type", help="Only requeue rows with this event_type.")
    parser.add_argument(
        "--min-age-minutes",
        type=int,
        default=0,
        help="Only requeue rows whose failed_at is older than N minutes "
        "(backoff so a still-recovering downstream isn't hammered).",
    )
    parser.add_argument("--limit", type=int, help="Cap the number of rows requeued.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Requeue ALL matching FAILED rows (required to act without --id/--event-type).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List rows that would be requeued; do not write."
    )
    args = parser.parse_args()

    if not args.id and not args.event_type and not args.all:
        parser.error("refusing to requeue without a selector: pass --id, --event-type, or --all")

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
