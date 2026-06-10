from sqlalchemy import Column, Integer, SmallInteger, Table, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP

from app.domain.entities.insight import Insight
from app.outbound.persistence_sqla.mappings._types import (
    BudgetSummarySnapshotType,
    ContextQualityType,
    InsightIdType,
    InsightStatusType,
    PeriodType,
    UserIdType,
)
from app.outbound.persistence_sqla.registry import mapper_registry

insights = Table(
    "insights",
    mapper_registry.metadata,
    Column("id", InsightIdType(), primary_key=True),
    Column("user_id", UserIdType(), nullable=False),
    Column("period", PeriodType(), nullable=False),
    Column("period_year", Integer(), nullable=False),
    Column("period_month", Integer(), nullable=False),
    Column("status", InsightStatusType(), nullable=False),
    Column("context_quality", ContextQualityType(), nullable=True),
    Column("title", Text(), nullable=True),
    Column("description", Text(), nullable=True),
    Column("impact_score", SmallInteger(), nullable=True),
    Column("generated_at", TIMESTAMP(timezone=True), nullable=True),
    Column("error_message", Text(), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=True),
    Column("budget_summary", BudgetSummarySnapshotType(), nullable=True),
)


def map_insight() -> None:
    mapper_registry.map_imperatively(
        Insight,
        insights,
        properties={
            "id_": insights.c.id,
        },
    )
