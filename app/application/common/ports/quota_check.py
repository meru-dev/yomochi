from abc import abstractmethod
from enum import StrEnum
from typing import Protocol

from app.domain.value_objects.enums import Plan
from app.domain.value_objects.ids import UserId


class QuotaResource(StrEnum):
    TRANSACTIONS = "transactions"
    INSIGHTS = "insights"


class QuotaExceededError(Exception):
    def __init__(self, *, resource: QuotaResource, current: int, limit: int) -> None:
        self.resource = resource
        self.current = current
        self.limit = limit
        super().__init__(f"Quota exceeded for {resource}: {current}/{limit}")


class QuotaCheck(Protocol):
    @abstractmethod
    async def check_and_increment(
        self, user_id: UserId, resource: QuotaResource, plan: Plan
    ) -> None:
        """Check quota from source tables and raise QuotaExceededError if the limit is breached.

        Implementations must read from the same session/TX as the caller so the
        count is consistent with any in-flight inserts.
        """
