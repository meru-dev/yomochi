from datetime import date
from typing import Protocol

from app.domain.value_objects.ids import UserId


class ActiveUserReader(Protocol):
    async def recently_active_user_ids(self, since: date) -> list[UserId]:
        """Distinct users with at least one transaction dated on/after `since`."""
        ...
