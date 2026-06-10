from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.categories.use_cases.list_categories import (
    ListCategoriesQuery,
    ListCategoriesUseCase,
)
from app.application.common.ports.identity_context import IdentityContext
from app.domain.entities.category import Category

router = ErrorAwareRouter()


class CategoryItem(BaseModel):
    id: str
    name: str
    icon: str | None
    color: str | None
    is_system: bool
    parent_id: str | None
    type: str


class ListCategoriesResponse(BaseModel):
    items: list[CategoryItem]


def _serialize(cat: Category) -> CategoryItem:
    return CategoryItem(
        id=str(cat.id_),
        name=cat.name,
        icon=cat.icon,
        color=cat.color,
        is_system=cat.is_system,
        parent_id=str(cat.parent_id) if cat.parent_id is not None else None,
        type=cat.type.value,
    )


@router.get("", status_code=status.HTTP_200_OK, response_model=ListCategoriesResponse)
@inject
async def list_categories(
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[ListCategoriesUseCase],
) -> ListCategoriesResponse:
    result = await use_case(ListCategoriesQuery(user_id=identity.user_id))
    return ListCategoriesResponse(items=[_serialize(cat) for cat in result.categories])
