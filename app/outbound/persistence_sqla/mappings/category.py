import sqlalchemy as sa
from sqlalchemy import Boolean, Column, String, Table
from sqlalchemy.dialects.postgresql import TIMESTAMP

from app.domain.entities.category import Category
from app.outbound.persistence_sqla.mappings._types import (
    CategoryIdType,
    CategoryTypeType,
    UserIdType,
)
from app.outbound.persistence_sqla.registry import mapper_registry

categories = Table(
    "categories",
    mapper_registry.metadata,
    Column("id", CategoryIdType(), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("icon", String(10), nullable=True),
    Column("color", String(7), nullable=True),
    Column("is_system", Boolean(), nullable=False, default=False),
    Column("user_id", UserIdType(), nullable=True),
    Column("parent_id", CategoryIdType(), sa.ForeignKey("categories.id"), nullable=True),
    Column("type", CategoryTypeType(), nullable=False, default="expense"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
)


def map_category() -> None:
    mapper_registry.map_imperatively(
        Category,
        categories,
        properties={
            "id_": categories.c.id,
            "name": categories.c.name,
            "icon": categories.c.icon,
            "color": categories.c.color,
            "is_system": categories.c.is_system,
            "user_id": categories.c.user_id,
            "parent_id": categories.c.parent_id,
            "type": categories.c.type,
            "created_at": categories.c.created_at,
        },
    )
