import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.entities.category import Category
from app.domain.value_objects.ids import CategoryId, UserId
from app.outbound.persistence_sqla.mappings.category import categories


class SqlaCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, category: Category) -> None:
        try:
            await self._session.merge(category)
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_by_id(self, id_: CategoryId) -> Category | None:
        try:
            result = await self._session.execute(sa.select(Category).where(categories.c.id == id_))
            return result.scalars().first()
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_user_category_by_name(self, user_id: UserId, name: str) -> Category | None:
        try:
            result = await self._session.execute(
                sa.select(Category)
                .where(categories.c.user_id == user_id)
                .where(categories.c.name == name)
            )
            return result.scalars().first()
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def list_for_user(self, user_id: UserId) -> list[Category]:
        try:
            result = await self._session.execute(
                sa.select(Category)
                .where(
                    sa.or_(
                        categories.c.is_system.is_(True),
                        categories.c.user_id == user_id,
                    )
                )
                .order_by(
                    categories.c.is_system.desc(),
                    categories.c.name.asc(),
                )
            )
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            raise StorageError from exc
