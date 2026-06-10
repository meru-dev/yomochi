import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.users.audit_event import AuditEvent
from app.application.users.ports.audit_log import AuditLog
from app.application.users.ports.password_reset_token_store import PasswordResetTokenStore
from app.application.users.ports.session_store import SessionStore
from app.application.users.ports.user_repository import UserRepository
from app.domain.ports.password_hasher import PasswordHasher
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.password import RawPassword


class InvalidPasswordResetTokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ConfirmPasswordResetCommand:
    token: str
    new_password: str


class ConfirmPasswordResetUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        token_store: PasswordResetTokenStore,
        password_hasher: PasswordHasher,
        session_store: SessionStore,
        audit_log: AuditLog,
    ) -> None:
        self._user_repo = user_repo
        self._token_store = token_store
        self._password_hasher = password_hasher
        self._session_store = session_store
        self._audit_log = audit_log

    async def __call__(self, command: ConfirmPasswordResetCommand) -> None:
        token_hash = hashlib.sha256(command.token.encode()).hexdigest()
        token = await self._token_store.get_valid(token_hash)
        if token is None:
            raise InvalidPasswordResetTokenError()

        user = await self._user_repo.get_by_id(token.user_id)
        if user is None:
            raise InvalidPasswordResetTokenError()

        new_hash = await self._password_hasher.hash(RawPassword(command.new_password))
        user.change_password(new_hash)
        await self._user_repo.save(user)
        await self._token_store.invalidate(token.id_)
        await self._session_store.revoke_all(user.id_)
        await self._audit_log.record(
            AuditEvent(
                event_type=AuditEventType.PASSWORD_RESET_CONFIRMED,
                user_id=user.id_,
                occurred_at=datetime.now(UTC),
            )
        )
