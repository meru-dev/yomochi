import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.insights.chunk_retriever import SqlaChunkRetriever
from tests.integration.factories import register_and_login

pytestmark = pytest.mark.asyncio(loop_scope="module")
_PASS = "StrongPass123!"
_FAKE_EMBEDDING = "[" + ",".join(["0.1"] * 1536) + "]"


async def _get_user_id(db_url: str, email: str) -> uuid.UUID:
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        row = await conn.execute(sa.text("SELECT id FROM users WHERE email = :e"), {"e": email})
        uid = row.scalar_one()
    await engine.dispose()
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


async def _insert_portrait_chunk(db_url: str, user_id: uuid.UUID) -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                f"""
                INSERT INTO user_financial_chunks
                    (id, user_id, chunk_type, period_year, period_month,
                     content, embedding, semantic_hash, metadata, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :uid, 'user_portrait', 0, 0,
                     'Portrait content', '{_FAKE_EMBEDDING}'::vector,
                     'testhash', '{{"recent_year": 2026}}'::jsonb,
                     now(), now())
                ON CONFLICT (user_id, chunk_type, period_year, period_month) DO NOTHING
                """
            ),
            {"uid": str(user_id)},
        )
    await engine.dispose()


def _session_factory(db_url: str):
    engine = create_async_engine(db_url)
    return async_sessionmaker(engine, autoflush=False, expire_on_commit=False), engine


async def test_get_portrait_returns_chunk_when_exists(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "pqr-exists@test.com"
    await register_and_login(client, email=email, password=_PASS)
    db_url = integration_settings["database_settings"].database_url
    uid = await _get_user_id(db_url, email)
    await _insert_portrait_chunk(db_url, uid)

    sf, engine = _session_factory(db_url)
    try:
        async with sf.begin() as session:
            result = await SqlaChunkRetriever(session).get_portrait(UserId(uid))
        assert result is not None
        assert result.chunk_type == "user_portrait"
        assert result.content == "Portrait content"
        assert result.period_label == "portrait"
        assert result.metadata == {"recent_year": 2026}
    finally:
        await engine.dispose()


async def test_get_portrait_returns_none_when_absent(
    client: AsyncClient, integration_settings: dict
) -> None:
    email = "pqr-absent@test.com"
    await register_and_login(client, email=email, password=_PASS)
    db_url = integration_settings["database_settings"].database_url
    uid = await _get_user_id(db_url, email)

    sf, engine = _session_factory(db_url)
    try:
        async with sf.begin() as session:
            result = await SqlaChunkRetriever(session).get_portrait(UserId(uid))
        assert result is None
    finally:
        await engine.dispose()
