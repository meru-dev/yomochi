from typing import Any
from uuid import UUID

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator

from app.domain.value_objects.budget_summary_snapshot import BudgetSummarySnapshot
from app.domain.value_objects.email import Email
from app.domain.value_objects.enums import (
    CategoryType,
    ContextQuality,
    InsightStatus,
    Period,
    Plan,
    Recurrence,
    RecurringRuleStatus,
    TransactionType,
)
from app.domain.value_objects.ids import (
    CategoryId,
    InsightId,
    RecurringRuleId,
    TransactionId,
    UserId,
)
from app.domain.value_objects.password import UserPasswordHash


class UserIdType(TypeDecorator[UserId]):
    impl = PgUUID(as_uuid=True)
    cache_ok = True

    def process_bind_param(self, value: UserId | None, dialect: Dialect) -> UUID | None:
        return value.value if isinstance(value, UserId) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> UserId | None:
        if value is None:
            return None
        return UserId(value if isinstance(value, UUID) else UUID(str(value)))


class EmailType(TypeDecorator[Email]):
    impl = String(254)
    cache_ok = True

    def process_bind_param(self, value: Email | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, Email) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> Email | None:
        if value is None:
            return None
        return Email(value)


class UserPasswordHashType(TypeDecorator[UserPasswordHash]):
    impl = String(255)
    cache_ok = True

    def process_bind_param(self, value: UserPasswordHash | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, UserPasswordHash) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> UserPasswordHash | None:
        if value is None:
            return None
        return UserPasswordHash(value)


class PlanType(TypeDecorator[Plan]):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value: Plan | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, Plan) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> Plan | None:
        if value is None:
            return None
        return Plan(value)


class TransactionIdType(TypeDecorator[TransactionId]):
    impl = PgUUID(as_uuid=True)
    cache_ok = True

    def process_bind_param(self, value: TransactionId | None, dialect: Dialect) -> UUID | None:
        return value.value if isinstance(value, TransactionId) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> TransactionId | None:
        if value is None:
            return None
        return TransactionId(value if isinstance(value, UUID) else UUID(str(value)))


class CategoryIdType(TypeDecorator[CategoryId]):
    impl = PgUUID(as_uuid=True)
    cache_ok = True

    def process_bind_param(self, value: CategoryId | None, dialect: Dialect) -> UUID | None:
        return value.value if isinstance(value, CategoryId) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> CategoryId | None:
        if value is None:
            return None
        return CategoryId(value if isinstance(value, UUID) else UUID(str(value)))


class TransactionTypeType(TypeDecorator[TransactionType]):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value: TransactionType | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, TransactionType) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> TransactionType | None:
        if value is None:
            return None
        return TransactionType(value)


class CategoryTypeType(TypeDecorator[CategoryType]):
    impl = String(7)
    cache_ok = True

    def process_bind_param(self, value: CategoryType | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, CategoryType) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> CategoryType | None:
        if value is None:
            return None
        return CategoryType(value)


class InsightIdType(TypeDecorator[InsightId]):
    impl = PgUUID(as_uuid=True)
    cache_ok = True

    def process_bind_param(self, value: InsightId | None, dialect: Dialect) -> UUID | None:
        return value.value if isinstance(value, InsightId) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> InsightId | None:
        if value is None:
            return None
        return InsightId(value if isinstance(value, UUID) else UUID(str(value)))


class InsightStatusType(TypeDecorator[InsightStatus]):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value: InsightStatus | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, InsightStatus) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> InsightStatus | None:
        if value is None:
            return None
        return InsightStatus(value)


class ContextQualityType(TypeDecorator[ContextQuality]):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value: ContextQuality | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, ContextQuality) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> ContextQuality | None:
        if value is None:
            return None
        return ContextQuality(value)


class PeriodType(TypeDecorator[Period]):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value: Period | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, Period) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> Period | None:
        if value is None:
            return None
        return Period(value)


class RecurringRuleIdType(TypeDecorator[RecurringRuleId]):
    impl = PgUUID(as_uuid=True)
    cache_ok = True

    def process_bind_param(self, value: RecurringRuleId | None, dialect: Dialect) -> UUID | None:
        return value.value if isinstance(value, RecurringRuleId) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> RecurringRuleId | None:
        if value is None:
            return None
        return RecurringRuleId(value if isinstance(value, UUID) else UUID(str(value)))


class RecurringRuleStatusType(TypeDecorator[RecurringRuleStatus]):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value: RecurringRuleStatus | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, RecurringRuleStatus) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> RecurringRuleStatus | None:
        if value is None:
            return None
        return RecurringRuleStatus(value)


class RecurrenceType(TypeDecorator[Recurrence]):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value: Recurrence | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, Recurrence) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> Recurrence | None:
        if value is None:
            return None
        return Recurrence(value)


class BudgetSummarySnapshotType(TypeDecorator[BudgetSummarySnapshot]):
    impl = JSONB
    cache_ok = True

    def process_bind_param(
        self, value: BudgetSummarySnapshot | None, dialect: Dialect
    ) -> list[dict[str, Any]] | None:
        return value.to_json() if isinstance(value, BudgetSummarySnapshot) else None

    def process_result_value(self, value: Any, dialect: Dialect) -> BudgetSummarySnapshot | None:
        if value is None:
            return None
        return BudgetSummarySnapshot.from_json(value)
