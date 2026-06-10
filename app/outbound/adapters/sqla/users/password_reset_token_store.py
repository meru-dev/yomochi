from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.exceptions import StorageError
from app.application.users.password_reset_token import PasswordResetToken
from app.domain.value_objects.ids import PasswordResetTokenId, UserId
from app.outbound.persistence_sqla.mappings.password_reset_token import password_reset_tokens


class SqlaPasswordResetTokenStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, token: PasswordResetToken) -> None:
        try:
            await self._session.execute(
                password_reset_tokens.insert().values(
                    id=token.id_.value,
                    user_id=token.user_id.value,
                    token_hash=token.token_hash,
                    expires_at=token.expires_at,
                )
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def get_valid(self, token_hash: str) -> PasswordResetToken | None:
        try:
            now = datetime.now(UTC)
            row = (
                await self._session.execute(
                    select(password_reset_tokens).where(
                        password_reset_tokens.c.token_hash == token_hash,
                        password_reset_tokens.c.expires_at > now,
                    )
                )
            ).fetchone()
            if row is None:
                return None
            return PasswordResetToken(
                id_=PasswordResetTokenId(row.id),
                user_id=UserId(row.user_id),
                token_hash=row.token_hash,
                expires_at=row.expires_at,
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc

    async def invalidate(self, token_id: PasswordResetTokenId) -> None:
        try:
            await self._session.execute(
                delete(password_reset_tokens).where(password_reset_tokens.c.id == token_id.value)
            )
        except SQLAlchemyError as exc:
            raise StorageError from exc
