import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from app.domain.value_objects.enums import OutboxStatus
from app.outbound.persistence_sqla.registry import mapper_registry

outbox_events = sa.Table(
    "outbox_events",
    mapper_registry.metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("event_type", sa.String(100), nullable=False),
    sa.Column("aggregate_id", sa.String(36), nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("status", sa.String(20), nullable=False, server_default=OutboxStatus.PENDING),
    sa.Column("occurred_at", TIMESTAMP(timezone=True), nullable=False),
    sa.Column(
        "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")
    ),
    sa.Column("user_id", UUID(as_uuid=True), nullable=True),
    sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("last_error", sa.Text, nullable=True),
    sa.Column("failed_at", TIMESTAMP(timezone=True), nullable=True),
    sa.Column("trace_context", JSONB, nullable=True),
)
