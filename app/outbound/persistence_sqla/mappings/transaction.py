from decimal import Decimal

from sqlalchemy import Column, Date, Numeric, String, Table, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import composite

from app.domain.entities.transaction import Transaction
from app.domain.value_objects.money import Currency, Money
from app.outbound.persistence_sqla.mappings._types import (
    CategoryIdType,
    RecurringRuleIdType,
    TransactionIdType,
    TransactionTypeType,
    UserIdType,
)
from app.outbound.persistence_sqla.registry import mapper_registry

transactions = Table(
    "transactions",
    mapper_registry.metadata,
    Column("id", TransactionIdType(), primary_key=True),
    Column("user_id", UserIdType(), nullable=False),
    Column("amount_value", Numeric(precision=19, scale=4), nullable=False),
    Column("currency_code", String(3), nullable=False),
    Column("date", Date(), nullable=False),
    Column("type", TransactionTypeType(), nullable=False),
    Column("merchant", String(200), nullable=True),
    Column("notes", Text(), nullable=True),
    Column("category_id", CategoryIdType(), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=True),
    Column("recurring_rule_id", RecurringRuleIdType(), nullable=True),
)


def _money_factory(amount: Decimal, currency_code: str) -> Money:
    return Money(amount=amount, currency=Currency(currency_code))


def map_transaction() -> None:
    mapper_registry.map_imperatively(
        Transaction,
        transactions,
        properties={
            "id_": transactions.c.id,
            "user_id": transactions.c.user_id,
            "amount": composite(
                _money_factory, transactions.c.amount_value, transactions.c.currency_code
            ),
            "date": transactions.c.date,
            "type_": transactions.c.type,
            "merchant": transactions.c.merchant,
            "notes": transactions.c.notes,
            "category_id": transactions.c.category_id,
            "created_at": transactions.c.created_at,
            "updated_at": transactions.c.updated_at,
            "recurring_rule_id": transactions.c.recurring_rule_id,
        },
    )
