from collections.abc import Mapping
from typing import Final

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.common.ports.flusher import Flusher
from app.domain.exceptions.domain_errors import CategoryNameAlreadyExistsError
from app.outbound.persistence_sqla import constraint_names as cn

CONSTRAINT_TO_ERROR: Final[Mapping[str, type[Exception]]] = {
    cn.UQ_CATEGORIES_USER_ID_NAME: CategoryNameAlreadyExistsError,
}


class SqlaFlusher(Flusher):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as e:
            msg = str(e)
            for name, exc_type in CONSTRAINT_TO_ERROR.items():
                if name in msg:
                    raise exc_type("") from e
            raise StorageError from e
        except SQLAlchemyError as exc:
            raise StorageError from exc
