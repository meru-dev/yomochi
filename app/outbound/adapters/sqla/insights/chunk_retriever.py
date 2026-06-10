from calendar import month_name as calendar_month_name

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.insights.ports.chunk_retriever import RetrievedChunk
from app.domain.value_objects.ids import UserId


class SqlaChunkRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        user_id: UserId,
        query_embedding: list[float],
        monthly_top_k: int = 3,
        shift_top_k: int = 2,
    ) -> list[RetrievedChunk]:
        try:
            # Bind the embedding as a parameter (cast to vector inside SQL).
            # This keeps the prepared-statement cache hot and matches the chunk_writer
            # pattern. Embedding values are never interpolated into the SQL text.
            # hnsw.ef_search is set once per connection via an engine "connect" event
            # listener registered in providers.py / worker_providers.py.
            embedding_literal = f"[{','.join(str(v) for v in query_embedding)}]"

            union_stmt = sa.text(
                """
                (
                  SELECT content, chunk_type, period_year, period_month, metadata
                  FROM user_financial_chunks
                  WHERE user_id = :user_id
                    AND chunk_type = 'monthly_summary'
                    AND embedding IS NOT NULL
                  ORDER BY embedding <=> CAST(:embedding AS vector)
                  LIMIT :monthly_limit
                )
                UNION ALL
                (
                  SELECT content, chunk_type, period_year, period_month, metadata
                  FROM user_financial_chunks
                  WHERE user_id = :user_id
                    AND chunk_type = 'behavioral_shift'
                    AND embedding IS NOT NULL
                  ORDER BY embedding <=> CAST(:embedding AS vector)
                  LIMIT :shift_limit
                )
                """
            )
            params = {
                "user_id": user_id.value,
                "embedding": embedding_literal,
                "monthly_limit": monthly_top_k,
                "shift_limit": shift_top_k,
            }
            rows = (await self._session.execute(union_stmt, params)).fetchall()

            results: list[RetrievedChunk] = []
            for r in rows:
                label = f"{calendar_month_name[r.period_month]} {r.period_year}"
                results.append(
                    RetrievedChunk(
                        content=r.content,
                        chunk_type=r.chunk_type,
                        period_label=label,
                        metadata=r.metadata or {},
                    )
                )
            return results
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_portrait(self, user_id: UserId) -> RetrievedChunk | None:
        try:
            stmt = sa.text(
                """
                SELECT content, metadata
                FROM user_financial_chunks
                WHERE user_id = :user_id
                  AND chunk_type = 'user_portrait'
                  AND period_year = 0
                  AND period_month = 0
                """
            )
            row = (await self._session.execute(stmt, {"user_id": user_id.value})).fetchone()
            if row is None:
                return None
            return RetrievedChunk(
                content=row.content,
                chunk_type="user_portrait",
                period_label="portrait",
                metadata=row.metadata or {},
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc
