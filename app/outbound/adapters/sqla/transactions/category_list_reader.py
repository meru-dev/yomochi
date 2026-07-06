import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.transactions.ports.category_list_reader import CategoryListItem
from app.domain.value_objects.ids import CategoryId, UserId
from app.outbound.persistence_sqla.mappings.category import categories


class SqlaCategoryListReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: UserId) -> list[CategoryListItem]:
        try:
            rows = (
                await self._session.execute(
                    sa.select(categories.c.id, categories.c.name, categories.c.parent_id)
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
            ).all()
        except SQLAlchemyError as exc:
            raise StorageError from exc
        return [
            CategoryListItem(
                id_=str(r.id),
                name=r.name,
                parent_id=str(r.parent_id) if r.parent_id is not None else None,
            )
            for r in rows
        ]

    async def get_by_id_for_user(
        self, category_id: CategoryId, user_id: UserId
    ) -> CategoryListItem | None:
        try:
            result = await self._session.execute(
                sa.select(categories.c.id, categories.c.name, categories.c.parent_id)
                .where(categories.c.id == category_id)
                .where(
                    sa.or_(
                        categories.c.is_system.is_(True),
                        categories.c.user_id == user_id,
                    )
                )
            )
            row = result.first()
        except SQLAlchemyError as exc:
            raise StorageError from exc
        if row is None:
            return None
        return CategoryListItem(
            id_=str(row.id),
            name=row.name,
            parent_id=str(row.parent_id) if row.parent_id is not None else None,
        )
