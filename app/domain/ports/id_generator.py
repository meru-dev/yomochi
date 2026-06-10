from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.ids import (
    CategoryId,
    InsightId,
    PasswordResetTokenId,
    RecurringRuleId,
    SessionId,
    TransactionId,
    UserId,
)


class UserIdGenerator(Protocol):
    @abstractmethod
    def __call__(self) -> UserId: ...


class TransactionIdGenerator(Protocol):
    @abstractmethod
    def __call__(self) -> TransactionId: ...


class CategoryIdGenerator(Protocol):
    @abstractmethod
    def __call__(self) -> CategoryId: ...


class InsightIdGenerator(Protocol):
    @abstractmethod
    def __call__(self) -> InsightId: ...


class SessionIdGenerator(Protocol):
    @abstractmethod
    def __call__(self) -> SessionId: ...


class PasswordResetTokenIdGenerator(Protocol):
    @abstractmethod
    def __call__(self) -> PasswordResetTokenId: ...


class RecurringRuleIdGenerator(Protocol):
    @abstractmethod
    def __call__(self) -> RecurringRuleId: ...
