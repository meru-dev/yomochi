import sqlalchemy as sa
from sqlalchemy import Column, SmallInteger, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811

from app.outbound.persistence_sqla.registry import mapper_registry

user_financial_chunks = Table(
    "user_financial_chunks",
    mapper_registry.metadata,
    Column("id", PgUUID(as_uuid=True), nullable=False),
    Column("user_id", PgUUID(as_uuid=True), nullable=False),
    Column("chunk_type", String(30), nullable=False),
    Column("period_year", SmallInteger(), nullable=False),
    Column("period_month", SmallInteger(), nullable=False),
    Column("content", Text(), nullable=False),
    # embedding stored as text for portability; cast happens in SQL
    Column("embedding", sa.Text(), nullable=True),
    Column("semantic_hash", String(64), nullable=False),
    Column("metadata", JSONB(), nullable=False, server_default="{}"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=True),
)
