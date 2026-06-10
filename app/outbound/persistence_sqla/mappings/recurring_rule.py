from decimal import Decimal

from sqlalchemy import Column, Date, Numeric, SmallInteger, String, Table, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import composite

from app.domain.entities.recurring_rule import RecurringRule
from app.domain.value_objects.money import Currency, Money
from app.outbound.persistence_sqla.mappings._types import (
    CategoryIdType,
    RecurrenceType,
    RecurringRuleIdType,
    RecurringRuleStatusType,
    TransactionTypeType,
    UserIdType,
)
from app.outbound.persistence_sqla.registry import mapper_registry

recurring_rules = Table(
    "recurring_rules",
    mapper_registry.metadata,
    Column("id", RecurringRuleIdType(), primary_key=True),
    Column("user_id", UserIdType(), nullable=False),
    Column("amount_value", Numeric(precision=19, scale=4), nullable=False),
    Column("currency_code", String(3), nullable=False),
    Column("type", TransactionTypeType(), nullable=False),
    Column("merchant", String(200), nullable=True),
    Column("notes", Text(), nullable=True),
    Column("category_id", CategoryIdType(), nullable=True),
    Column("recurrence", RecurrenceType(), nullable=False),
    Column("day_of_month", SmallInteger(), nullable=True),
    Column("day_of_week", SmallInteger(), nullable=True),
    Column("month", SmallInteger(), nullable=True),
    Column("start_date", Date(), nullable=False),
    Column("end_date", Date(), nullable=True),
    Column("status", RecurringRuleStatusType(), nullable=False),
    Column("next_fire_date", Date(), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=True),
)


def _money_factory(amount: Decimal, currency_code: str) -> Money:
    return Money(amount=amount, currency=Currency(currency_code))


def map_recurring_rule() -> None:
    mapper_registry.map_imperatively(
        RecurringRule,
        recurring_rules,
        properties={
            "id_": recurring_rules.c.id,
            "user_id": recurring_rules.c.user_id,
            "amount": composite(
                _money_factory,
                recurring_rules.c.amount_value,
                recurring_rules.c.currency_code,
            ),
            "type_": recurring_rules.c.type,
            "merchant": recurring_rules.c.merchant,
            "notes": recurring_rules.c.notes,
            "category_id": recurring_rules.c.category_id,
            "recurrence": recurring_rules.c.recurrence,
            "day_of_month": recurring_rules.c.day_of_month,
            "day_of_week": recurring_rules.c.day_of_week,
            "month": recurring_rules.c.month,
            "start_date": recurring_rules.c.start_date,
            "end_date": recurring_rules.c.end_date,
            "status": recurring_rules.c.status,
            "next_fire_date": recurring_rules.c.next_fire_date,
            "created_at": recurring_rules.c.created_at,
            "updated_at": recurring_rules.c.updated_at,
        },
    )
