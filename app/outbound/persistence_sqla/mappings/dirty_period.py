import sqlalchemy as sa
from sqlalchemy import Column, Integer, Table
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811

from app.outbound.persistence_sqla.registry import mapper_registry

dirty_periods = Table(
    "dirty_periods",
    mapper_registry.metadata,
    Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
    Column("user_id", PgUUID(as_uuid=True), nullable=False),
    Column("year", Integer(), nullable=False),
    Column("month", Integer(), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
)
