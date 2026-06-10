from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import status
from fastapi_error_map import ErrorAwareRouter
from pydantic import BaseModel

from app.application.categories.use_cases.create_category import (
    CreateCategoryCommand,
    CreateCategoryUseCase,
)
from app.application.common.ports.identity_context import IdentityContext
from app.domain.exceptions.domain_errors import (
    CategoryNameAlreadyExistsError,
    CategoryParentIsLeafError,
    CategoryParentNotFoundError,
    CategoryTypeMismatchError,
)
from app.domain.value_objects.enums import CategoryType
from app.domain.value_objects.ids import CategoryId
from app.inbound.http.auth.identity import UnauthenticatedError

router = ErrorAwareRouter()


class CreateCategoryRequest(BaseModel):
    name: str
    type: str
    parent_id: str | None = None
    icon: str | None = None
    color: str | None = None


class CreateCategoryResponse(BaseModel):
    id: str


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateCategoryResponse,
    error_map={
        UnauthenticatedError: status.HTTP_401_UNAUTHORIZED,
        CategoryNameAlreadyExistsError: status.HTTP_409_CONFLICT,
        CategoryParentNotFoundError: status.HTTP_404_NOT_FOUND,
        CategoryParentIsLeafError: status.HTTP_422_UNPROCESSABLE_CONTENT,
        CategoryTypeMismatchError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    },
)
@inject
async def create_category(
    body: CreateCategoryRequest,
    identity: FromDishka[IdentityContext],
    use_case: FromDishka[CreateCategoryUseCase],
) -> CreateCategoryResponse:
    parent_id = CategoryId(UUID(body.parent_id)) if body.parent_id else None
    result = await use_case(
        CreateCategoryCommand(
            user_id=identity.user_id,
            name=body.name,
            type=CategoryType(body.type),
            parent_id=parent_id,
            icon=body.icon,
            color=body.color,
        )
    )
    return CreateCategoryResponse(id=result.category_id)
