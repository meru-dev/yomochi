import uuid

from app.domain.value_objects.ids import (
    CategoryId,
    InsightId,
    PasswordResetTokenId,
    SessionId,
    TransactionId,
    UserId,
)


class FakeUserIdGenerator:
    def __init__(self, fixed: uuid.UUID | None = None) -> None:
        self._fixed = fixed

    def __call__(self) -> UserId:
        return UserId(self._fixed or uuid.uuid4())


class FakeTransactionIdGenerator:
    def __init__(self, fixed: uuid.UUID | None = None) -> None:
        self._fixed = fixed

    def __call__(self) -> TransactionId:
        return TransactionId(self._fixed or uuid.uuid4())


class FakeCategoryIdGenerator:
    def __init__(self, fixed: uuid.UUID | None = None) -> None:
        self._fixed = fixed

    def __call__(self) -> CategoryId:
        return CategoryId(self._fixed or uuid.uuid4())


class FakeInsightIdGenerator:
    def __init__(self, fixed: uuid.UUID | None = None) -> None:
        self._fixed = fixed

    def __call__(self) -> InsightId:
        return InsightId(self._fixed or uuid.uuid4())


class FakeSessionIdGenerator:
    def __init__(self, fixed: uuid.UUID | None = None) -> None:
        self._fixed = fixed

    def __call__(self) -> SessionId:
        return SessionId(self._fixed or uuid.uuid4())


class FakePasswordResetTokenIdGenerator:
    def __init__(self, fixed: uuid.UUID | None = None) -> None:
        self._fixed = fixed

    def __call__(self) -> PasswordResetTokenId:
        return PasswordResetTokenId(self._fixed or uuid.uuid4())
