from dataclasses import dataclass
from datetime import datetime

from app.domain.entities.base import EntityMixin
from app.domain.exceptions.domain_errors import CategoryIsGroupError, CategoryParentIsLeafError
from app.domain.value_objects.enums import CategoryType
from app.domain.value_objects.ids import CategoryId, UserId


@dataclass(eq=False)
class Category(EntityMixin):
    id_: CategoryId
    name: str
    icon: str | None
    color: str | None
    is_system: bool
    user_id: UserId | None
    parent_id: CategoryId | None
    type: CategoryType
    created_at: datetime

    @property
    def is_group(self) -> bool:
        return self.parent_id is None

    @property
    def is_leaf(self) -> bool:
        return self.parent_id is not None

    def validate_assignable(self) -> None:
        """Raise if this category cannot be assigned to a transaction (groups are not assignable)."""
        if self.is_group:
            raise CategoryIsGroupError(str(self.id_))

    def validate_can_be_parent(self) -> None:
        """Raise if this category cannot be a parent (leaves cannot have children)."""
        if self.is_leaf:
            raise CategoryParentIsLeafError(str(self.id_))
