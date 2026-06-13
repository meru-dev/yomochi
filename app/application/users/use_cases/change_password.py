from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.common.audit_event import AuditEvent
from app.application.common.ports.audit_log import AuditLog
from app.application.users.ports.session_store import SessionStore
from app.application.users.ports.user_repository import UserRepository
from app.domain.ports.password_hasher import PasswordHasher
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.password import RawPassword


class InvalidCurrentPasswordError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ChangePasswordCommand:
    user_id: UserId
    current_password: str
    new_password: str


class ChangePasswordUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        password_hasher: PasswordHasher,
        session_store: SessionStore,
        audit_log: AuditLog,
    ) -> None:
        self._user_repo = user_repo
        self._password_hasher = password_hasher
        self._session_store = session_store
        self._audit_log = audit_log

    async def __call__(self, command: ChangePasswordCommand) -> None:
        user = await self._user_repo.get_by_id(command.user_id)
        if user is None:
            raise UserNotFoundError(str(command.user_id))

        current = RawPassword(command.current_password)
        if not await self._password_hasher.verify(current, user.password_hash):
            raise InvalidCurrentPasswordError()

        new_hash = await self._password_hasher.hash(RawPassword(command.new_password))
        user.change_password(new_hash)
        await self._user_repo.save(user)
        await self._session_store.revoke_all(command.user_id)
        await self._audit_log.record(
            AuditEvent(
                event_type=AuditEventType.PASSWORD_CHANGED,
                user_id=command.user_id,
                occurred_at=datetime.now(UTC),
            )
        )
