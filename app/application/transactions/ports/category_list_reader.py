from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol

from app.domain.exceptions.domain_errors import CategoryIsGroupError
from app.domain.value_objects.ids import CategoryId, UserId


@dataclass(frozen=True, slots=True)
class CategoryListItem:
    id_: str
    name: str
    parent_id: str | None  # None = group; not None = leaf

    def validate_assignable(self) -> None:
        if self.parent_id is None:
            raise CategoryIsGroupError(self.id_)


class CategoryListReader(Protocol):
    """Transactions-BC-owned port for reading category data needed by AI parse-text
    and transaction category validation. Does not depend on the Category entity."""

    @abstractmethod
    async def list_for_user(self, user_id: UserId) -> list[CategoryListItem]: ...

    @abstractmethod
    async def get_by_id_for_user(
        self, category_id: CategoryId, user_id: UserId
    ) -> CategoryListItem | None: ...
