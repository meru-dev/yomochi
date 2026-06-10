from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.categories.ports.category_repository import CategoryRepository
from app.application.common.ports.flusher import Flusher
from app.domain.entities.category import Category
from app.domain.exceptions.domain_errors import (
    CategoryNameAlreadyExistsError,
    CategoryParentNotFoundError,
    CategoryTypeMismatchError,
)
from app.domain.ports.id_generator import CategoryIdGenerator
from app.domain.value_objects.enums import CategoryType
from app.domain.value_objects.ids import CategoryId, UserId


@dataclass(frozen=True, slots=True)
class CreateCategoryCommand:
    user_id: UserId
    name: str
    type: CategoryType
    parent_id: CategoryId | None = None
    icon: str | None = None
    color: str | None = None


@dataclass(frozen=True, slots=True)
class CreateCategoryResult:
    category_id: str


class CreateCategoryUseCase:
    def __init__(
        self,
        category_repo: CategoryRepository,
        flusher: Flusher,
        id_generator: CategoryIdGenerator,
    ) -> None:
        self._category_repo = category_repo
        self._flusher = flusher
        self._id_generator = id_generator

    async def __call__(self, command: CreateCategoryCommand) -> CreateCategoryResult:
        if command.parent_id is not None:
            parent = await self._category_repo.get_by_id(command.parent_id)
            if parent is None:
                raise CategoryParentNotFoundError(str(command.parent_id))
            parent.validate_can_be_parent()
            if parent.type != command.type:
                raise CategoryTypeMismatchError()

        existing = await self._category_repo.get_user_category_by_name(
            command.user_id, command.name
        )
        if existing is not None:
            raise CategoryNameAlreadyExistsError(command.name)

        category = Category(
            id_=self._id_generator(),
            name=command.name,
            icon=command.icon,
            color=command.color,
            is_system=False,
            user_id=command.user_id,
            parent_id=command.parent_id,
            type=command.type,
            created_at=datetime.now(UTC),
        )
        await self._category_repo.save(category)
        await self._flusher.flush()
        return CreateCategoryResult(category_id=str(category.id_))
