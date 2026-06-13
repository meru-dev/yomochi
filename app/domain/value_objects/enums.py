from enum import StrEnum


class Plan(StrEnum):
    FREE = "free"
    DEMO = "demo"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class CategoryType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Recurrence(StrEnum):
    NONE = "none"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class Period(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class InsightStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ContextQuality(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class AuditEventType(StrEnum):
    USER_REGISTERED = "user_registered"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    PASSWORD_CHANGED = "password_changed"  # noqa: S105
    PASSWORD_RESET_REQUESTED = "password_reset_requested"  # noqa: S105
    PASSWORD_RESET_CONFIRMED = "password_reset_confirmed"  # noqa: S105
    SESSION_REVOKED = "session_revoked"
    TRANSACTION_CREATED = "transaction_created"
    TRANSACTION_UPDATED = "transaction_updated"
    TRANSACTION_DELETED = "transaction_deleted"


class RecurringRuleStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
