from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.ids import UserId


class TransactionReader(Protocol):
    """Consumer-owned read port for the insights context.

    Reads directly from the transactions table without crossing bounded-context
    application boundaries. See CODING_STANDARDS §3.4 Pattern 1.
    """

    @abstractmethod
    async def count_for_period(self, user_id: UserId, year: int, month: int) -> int: ...
