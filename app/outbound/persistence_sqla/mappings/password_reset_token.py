from sqlalchemy import Column, String, Table
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811

from app.outbound.persistence_sqla.registry import mapper_registry

password_reset_tokens = Table(
    "password_reset_tokens",
    mapper_registry.metadata,
    Column("id", PgUUID(as_uuid=True), primary_key=True),
    Column("user_id", PgUUID(as_uuid=True), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
)
