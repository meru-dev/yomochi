from abc import abstractmethod
from typing import Protocol

from app.domain.entities.category import Category
from app.domain.value_objects.ids import CategoryId, UserId


class CategoryRepository(Protocol):
    @abstractmethod
    async def save(self, category: Category) -> None: ...

    @abstractmethod
    async def get_by_id(self, id_: CategoryId) -> Category | None: ...

    @abstractmethod
    async def get_user_category_by_name(self, user_id: UserId, name: str) -> Category | None: ...

    @abstractmethod
    async def list_for_user(self, user_id: UserId) -> list[Category]: ...
