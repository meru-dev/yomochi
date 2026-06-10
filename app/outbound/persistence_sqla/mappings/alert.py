import sqlalchemy as sa
from sqlalchemy import Column, SmallInteger, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811

from app.outbound.persistence_sqla.registry import mapper_registry

user_alerts = Table(
    "user_alerts",
    mapper_registry.metadata,
    Column("id", PgUUID(as_uuid=True), primary_key=True),
    Column("user_id", PgUUID(as_uuid=True), nullable=False),
    Column("type", sa.String(30), nullable=False),
    Column("subtype", sa.String(100), nullable=False),
    Column("title", Text(), nullable=False),
    Column("body", Text(), nullable=False),
    Column("metadata", JSONB(), nullable=False),
    Column("period_year", SmallInteger(), nullable=False),
    Column("period_month", SmallInteger(), nullable=False),
    Column("is_read", sa.Boolean(), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
)
