from abc import abstractmethod
from typing import Protocol

from app.domain.value_objects.enums import Plan
from app.domain.value_objects.ids import UserId


class UserPlanLookup(Protocol):
    """Resolve a user's plan without exposing the full User aggregate.

    Lives in `common/` so transactions + insights can consume it without
    importing across bounded contexts.
    """

    @abstractmethod
    async def get_plan(self, user_id: UserId) -> Plan: ...
