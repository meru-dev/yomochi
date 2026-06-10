from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.domain.entities.user import User
from app.domain.value_objects.email import Email
from app.domain.value_objects.ids import UserId
from app.outbound.persistence_sqla.mappings.user import users


class SqlaUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user: User) -> None:
        try:
            await self._session.merge(user)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_by_id(self, user_id: UserId) -> User | None:
        try:
            return await self._session.get(User, user_id)
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_by_email(self, email: Email) -> User | None:
        try:
            result = await self._session.execute(select(User).where(users.c.email == email))
            return result.scalars().first()
        except SQLAlchemyError as exc:
            raise StorageError from exc
