from uuid import UUID

import uuid_utils

from app.domain.value_objects.ids import (
    CategoryId,
    InsightId,
    PasswordResetTokenId,
    RecurringRuleId,
    SessionId,
    TransactionId,
    UserId,
)


def _uuid7() -> UUID:
    return UUID(str(uuid_utils.uuid7()))


class Uuid7UserIdGenerator:
    def __call__(self) -> UserId:
        return UserId(_uuid7())


class Uuid7TransactionIdGenerator:
    def __call__(self) -> TransactionId:
        return TransactionId(_uuid7())


class Uuid7CategoryIdGenerator:
    def __call__(self) -> CategoryId:
        return CategoryId(_uuid7())


class Uuid7InsightIdGenerator:
    def __call__(self) -> InsightId:
        return InsightId(_uuid7())


class Uuid7SessionIdGenerator:
    def __call__(self) -> SessionId:
        return SessionId(_uuid7())


class Uuid7PasswordResetTokenIdGenerator:
    def __call__(self) -> PasswordResetTokenId:
        return PasswordResetTokenId(_uuid7())


class Uuid7RecurringRuleIdGenerator:
    def __call__(self) -> RecurringRuleId:
        return RecurringRuleId(_uuid7())


class Uuid7ChatTurnIdGenerator:
    def __call__(self) -> UUID:
        return _uuid7()
