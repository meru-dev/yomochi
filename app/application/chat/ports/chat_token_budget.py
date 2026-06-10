from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.ids import UserId


class ChatTokenBudgetExceededError(Exception):
    def __init__(self, *, current: int, limit: int) -> None:
        self.current = current
        self.limit = limit
        super().__init__(f"Daily chat token budget exceeded ({current}/{limit}).")


class ChatTokenBudget(Protocol):
    @abstractmethod
    async def check(self, user_id: UserId) -> None:
        """Raise ChatTokenBudgetExceededError if the user is at/over the daily cap."""

    @abstractmethod
    async def record(self, user_id: UserId, tokens: int) -> None:
        """Increment the user's daily token counter. No-op for tokens <= 0."""
