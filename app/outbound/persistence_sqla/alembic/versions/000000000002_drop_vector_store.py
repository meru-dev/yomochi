"""Drop the vector-store schema (final Phase-B step).

Revision ID: 000000000002
Revises: 000000000001_init
Create Date: 2026-06-21

The vector-store subsystem (semantic RAG over user financial chunks) was removed:
chat now uses function-calling and insight generation is deterministic. The SQLA
mappings were deleted in Task 5b; this migration drops the now-unused physical
schema:

- user_financial_chunks (hash-partitioned, 16 parts) + its HNSW index — held the
  ONLY pgvector `vector` column in the database.
- dirty_periods — the re-embedding work queue.
- portrait_queue — the portrait-refresh work queue.
- the `vector` extension (no other table uses it).

KEPT (used by chat's search_transactions): the `pg_trgm` extension and the GIN
trigram indexes on transactions.merchant / transactions.notes.

⚠️ DESTRUCTIVE: this drops tables. The data is DERIVED (rebuildable from
transactions), so there is no source-of-truth loss, but take a DB snapshot before
running this against any real database. The downgrade() recreates the schema in its
identical post-init shape (empty tables) so the stairway test round-trips; it does
NOT restore data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000000000002_drop_vector_store"
down_revision: str | None = "000000000001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:
    # Drop the partitioned vector table (CASCADE removes its 16 partitions, the
    # HNSW + unique indexes, and fk_chunks_user_id_users) BEFORE dropping the
    # extension that supplied its `vector` column type.
    op.execute("DROP TABLE IF EXISTS user_financial_chunks CASCADE")
    op.drop_table("dirty_periods")
    op.drop_table("portrait_queue")
    # The `vector` column lived only in user_financial_chunks; safe to drop now.
    op.execute("DROP EXTENSION IF EXISTS vector")
    # pg_trgm and the GIN trigram indexes on transactions deliberately SURVIVE.


# ── downgrade ─────────────────────────────────────────────────────────────────
#
# Recreates the three tables EXACTLY as the init migration (000000000001) built
# them, so the post-init structure is restored. DDL copied verbatim from init.
# Tables come back empty — only the schema round-trips (acceptable for stairway).

def downgrade() -> None:
    # The `vector` type is required before recreating user_financial_chunks.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── dirty_periods ─────────────────────────────────────────────────────────
    op.create_table(
        "dirty_periods",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_dirty_periods_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "year", "month", name="uq_dirty_periods_user_year_month"),
    )

    # ── user_financial_chunks (hash-partitioned 16 parts) ─────────────────────
    op.execute(
        """
        CREATE TABLE user_financial_chunks (
            id           UUID         NOT NULL DEFAULT gen_random_uuid(),
            user_id      UUID         NOT NULL,
            chunk_type   VARCHAR(30)  NOT NULL,
            period_year  SMALLINT     NOT NULL,
            period_month SMALLINT     NOT NULL,
            content      TEXT         NOT NULL,
            embedding    VECTOR(1536),
            semantic_hash VARCHAR(64) NOT NULL,
            metadata     JSONB        NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ,
            PRIMARY KEY (id, user_id)
        ) PARTITION BY HASH (user_id)
        """
    )
    for i in range(16):
        op.execute(
            f"CREATE TABLE user_financial_chunks_{i}"
            f" PARTITION OF user_financial_chunks"
            f" FOR VALUES WITH (modulus 16, remainder {i})"
        )
    op.execute(
        "CREATE UNIQUE INDEX uq_chunks_user_type_period"
        " ON user_financial_chunks (user_id, chunk_type, period_year, period_month)"
    )
    op.execute(
        "CREATE INDEX ix_chunks_user_id_embedding"
        " ON user_financial_chunks"
        " USING hnsw (embedding vector_cosine_ops)"
        " WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "ALTER TABLE user_financial_chunks"
        " ADD CONSTRAINT fk_chunks_user_id_users"
        " FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
    )

    # ── portrait_queue ────────────────────────────────────────────────────────
    op.create_table(
        "portrait_queue",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "marked_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_portrait_queue_user_id_users",
            ondelete="CASCADE",
        ),
    )
