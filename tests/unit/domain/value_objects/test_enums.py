from app.domain.value_objects.enums import (
    AuditEventType,
    ContextQuality,
    InsightStatus,
    Period,
    Plan,
    Recurrence,
    TransactionPriority,
    TransactionType,
)


def test_plan_values() -> None:
    assert Plan.FREE.value == "free"


def test_transaction_type_values() -> None:
    assert TransactionType.INCOME.value == "income"
    assert TransactionType.EXPENSE.value == "expense"


def test_transaction_priority_values() -> None:
    assert TransactionPriority.LOW.value == "low"
    assert TransactionPriority.MEDIUM.value == "medium"
    assert TransactionPriority.HIGH.value == "high"


def test_recurrence_values() -> None:
    assert Recurrence.NONE.value == "none"
    assert Recurrence.WEEKLY.value == "weekly"
    assert Recurrence.MONTHLY.value == "monthly"
    assert Recurrence.YEARLY.value == "yearly"


def test_period_values() -> None:
    assert Period.WEEKLY.value == "weekly"
    assert Period.MONTHLY.value == "monthly"


def test_insight_status_values() -> None:
    assert InsightStatus.PENDING.value == "pending"
    assert InsightStatus.QUEUED.value == "queued"
    assert InsightStatus.PROCESSING.value == "processing"
    assert InsightStatus.COMPLETED.value == "completed"
    assert InsightStatus.FAILED.value == "failed"


def test_context_quality_values() -> None:
    assert ContextQuality.FULL.value == "full"
    assert ContextQuality.PARTIAL.value == "partial"
    assert ContextQuality.NONE.value == "none"


def test_audit_event_type_values() -> None:
    assert AuditEventType.USER_REGISTERED.value == "user_registered"
    assert AuditEventType.USER_LOGIN.value == "user_login"
    assert AuditEventType.USER_LOGOUT.value == "user_logout"
    assert AuditEventType.PASSWORD_CHANGED.value == "password_changed"
    assert AuditEventType.PASSWORD_RESET_REQUESTED.value == "password_reset_requested"
    assert AuditEventType.PASSWORD_RESET_CONFIRMED.value == "password_reset_confirmed"
    assert AuditEventType.SESSION_REVOKED.value == "session_revoked"


def test_enums_are_strings() -> None:
    assert isinstance(Plan.FREE, str)
    assert isinstance(TransactionType.EXPENSE, str)
