from dataclasses import dataclass

from app.application.categories.ports.category_repository import CategoryRepository
from app.domain.entities.category import Category
from app.domain.value_objects.ids import UserId


@dataclass(frozen=True, slots=True)
class ListCategoriesQuery:
    user_id: UserId


@dataclass(frozen=True, slots=True)
class ListCategoriesResult:
    categories: tuple[Category, ...]


class ListCategoriesUseCase:
    def __init__(self, category_repo: CategoryRepository) -> None:
        self._category_repo = category_repo

    async def __call__(self, query: ListCategoriesQuery) -> ListCategoriesResult:
        categories = await self._category_repo.list_for_user(query.user_id)
        return ListCategoriesResult(categories=tuple(categories))
