from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import TIMESTAMP

from app.domain.entities.user import User
from app.domain.value_objects.enums import Plan
from app.outbound.persistence_sqla.mappings._types import (
    EmailType,
    PlanType,
    UserIdType,
    UserPasswordHashType,
)
from app.outbound.persistence_sqla.registry import mapper_registry

users = Table(
    "users",
    mapper_registry.metadata,
    Column("id", UserIdType(), primary_key=True),
    Column("email", EmailType(), nullable=False),
    Column("password_hash", UserPasswordHashType(), nullable=False),
    Column("plan", PlanType(), nullable=False, server_default=Plan.FREE.value),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
)


def map_user() -> None:
    mapper_registry.map_imperatively(
        User,
        users,
        properties={
            "id_": users.c.id,
            "email": users.c.email,
            "password_hash": users.c.password_hash,
            "plan": users.c.plan,
            "created_at": users.c.created_at,
        },
    )
