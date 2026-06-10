import json
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.insights.ports.chunk_writer import ChunkToWrite
from app.domain.value_objects.ids import UserId

_EXPECTED_DIM = 1536


class SqlaChunkWriter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, chunk: ChunkToWrite) -> None:
        if len(chunk.embedding) != _EXPECTED_DIM:
            msg = f"Expected {_EXPECTED_DIM}-dimensional embedding, got {len(chunk.embedding)}"
            raise ValueError(msg)
        try:
            embedding_literal = f"[{','.join(str(v) for v in chunk.embedding)}]"
            stmt = sa.text(
                """
                INSERT INTO user_financial_chunks
                    (id, user_id, chunk_type, period_year, period_month,
                     content, embedding, semantic_hash, metadata, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :user_id, :chunk_type, :period_year, :period_month,
                     :content, CAST(:embedding AS vector), :semantic_hash, CAST(:metadata AS jsonb),
                     :created_at, :updated_at)
                ON CONFLICT (user_id, chunk_type, period_year, period_month)
                DO UPDATE SET
                    content       = EXCLUDED.content,
                    embedding     = EXCLUDED.embedding,
                    semantic_hash = EXCLUDED.semantic_hash,
                    metadata      = EXCLUDED.metadata,
                    updated_at    = EXCLUDED.updated_at
                WHERE user_financial_chunks.semantic_hash != EXCLUDED.semantic_hash
                """
            )
            now = datetime.now(UTC)
            await self._session.execute(
                stmt,
                {
                    "user_id": chunk.user_id.value,
                    "chunk_type": chunk.chunk_type,
                    "period_year": chunk.period_year,
                    "period_month": chunk.period_month,
                    "content": chunk.content,
                    "embedding": embedding_literal,
                    "semantic_hash": chunk.semantic_hash,
                    "metadata": json.dumps(chunk.metadata),
                    "created_at": now,
                    "updated_at": now,
                },
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def delete_for_period(self, user_id: UserId, year: int, month: int) -> None:
        try:
            await self._session.execute(
                sa.text(
                    """
                    DELETE FROM user_financial_chunks
                    WHERE user_id = :user_id
                      AND period_year = :year
                      AND period_month = :month
                    """
                ),
                {"user_id": user_id.value, "year": year, "month": month},
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc
