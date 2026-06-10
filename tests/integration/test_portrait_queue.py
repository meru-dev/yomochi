import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.insights.portrait_queue import SqlaPortraitQueue
from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")
_PASS = "StrongPass123!"


async def _get_user_id(db_url: str, email: str) -> uuid.UUID:
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        row = await conn.execute(sa.text("SELECT id FROM users WHERE email = :e"), {"e": email})
        uid = row.scalar_one()
    await engine.dispose()
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


def _session_factory(db_url: str):
    engine = create_async_engine(db_url)
    sf = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)
    return sf, engine


async def test_pop_dirty_empty_queue_returns_empty(
    client: AsyncClient, integration_settings: dict
) -> None:
    db_url = integration_settings["database_settings"].database_url
    sf, engine = _session_factory(db_url)
    try:
        async with sf.begin() as session:
            result = await SqlaPortraitQueue(session).pop_dirty(limit=10)
        assert result == []
    finally:
        await engine.dispose()


async def test_pop_dirty_returns_user_and_clears_queue(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "pq-pop@test.com"
    await register_and_login(client, email=email, password=_PASS)
    db_url = integration_settings["database_settings"].database_url
    uid = await _get_user_id(db_url, email)

    seed_engine = create_async_engine(db_url)
    async with seed_engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO portrait_queue (user_id) VALUES (:uid) ON CONFLICT DO NOTHING"),
            {"uid": str(uid)},
        )
    await seed_engine.dispose()

    sf, engine = _session_factory(db_url)
    try:
        async with sf.begin() as session:
            result = await SqlaPortraitQueue(session).pop_dirty(limit=10)

        assert UserId(uid) in result

        check_engine = create_async_engine(db_url)
        async with check_engine.connect() as conn:
            count = await conn.execute(
                sa.text("SELECT COUNT(*) FROM portrait_queue WHERE user_id = :uid"),
                {"uid": str(uid)},
            )
            assert count.scalar() == 0
        await check_engine.dispose()
    finally:
        await engine.dispose()


async def test_mark_all_dirty_queues_all_users(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "pq-mark@test.com"
    await register_and_login(client, email=email, password=_PASS)
    db_url = integration_settings["database_settings"].database_url
    uid = await _get_user_id(db_url, email)

    sf, engine = _session_factory(db_url)
    try:
        async with sf.begin() as session:
            count = await SqlaPortraitQueue(session).mark_all_dirty()
        assert count >= 1

        check_engine = create_async_engine(db_url)
        async with check_engine.connect() as conn:
            in_queue = await conn.execute(
                sa.text("SELECT COUNT(*) FROM portrait_queue WHERE user_id = :uid"),
                {"uid": str(uid)},
            )
            assert in_queue.scalar() == 1
        await check_engine.dispose()
    finally:
        await engine.dispose()


async def test_mark_all_dirty_is_idempotent(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "pq-idem@test.com"
    await register_and_login(client, email=email, password=_PASS)
    db_url = integration_settings["database_settings"].database_url

    sf, engine = _session_factory(db_url)
    try:
        async with sf.begin() as s1:
            c1 = await SqlaPortraitQueue(s1).mark_all_dirty()
        async with sf.begin() as s2:
            c2 = await SqlaPortraitQueue(s2).mark_all_dirty()
        assert c1 == c2
    finally:
        await engine.dispose()


async def test_user_deletion_cascades_to_portrait_queue(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "pq-cascade@test.com"
    await register_and_login(client, email=email, password=_PASS)
    db_url = integration_settings["database_settings"].database_url
    uid = await _get_user_id(db_url, email)

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO portrait_queue (user_id) VALUES (:uid) ON CONFLICT DO NOTHING"),
            {"uid": str(uid)},
        )
        await conn.execute(sa.text("DELETE FROM users WHERE id = :uid"), {"uid": str(uid)})
        count = await conn.execute(
            sa.text("SELECT COUNT(*) FROM portrait_queue WHERE user_id = :uid"),
            {"uid": str(uid)},
        )
        assert count.scalar() == 0
    await engine.dispose()
