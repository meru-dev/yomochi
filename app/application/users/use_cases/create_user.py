from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.users.audit_event import AuditEvent
from app.application.users.ports.audit_log import AuditLog
from app.application.users.ports.user_repository import UserRepository
from app.domain.entities.user import User
from app.domain.ports.id_generator import UserIdGenerator
from app.domain.ports.password_hasher import PasswordHasher
from app.domain.value_objects.email import Email
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.password import RawPassword


class UserAlreadyExistsError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreateUserCommand:
    email: str
    raw_password: str


@dataclass(frozen=True, slots=True)
class CreateUserResult:
    user_id: UserId


class CreateUserUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        password_hasher: PasswordHasher,
        id_generator: UserIdGenerator,
        audit_log: AuditLog,
    ) -> None:
        self._user_repo = user_repo
        self._password_hasher = password_hasher
        self._id_generator = id_generator
        self._audit_log = audit_log

    async def __call__(self, command: CreateUserCommand) -> CreateUserResult:
        email = Email(command.email)
        password = RawPassword(command.raw_password)

        if await self._user_repo.get_by_email(email) is not None:
            raise UserAlreadyExistsError(str(email))

        password_hash = await self._password_hasher.hash(password)
        now = datetime.now(UTC)
        user = User(
            id_=self._id_generator(),
            email=email,
            password_hash=password_hash,
            created_at=now,
        )
        await self._user_repo.save(user)
        await self._audit_log.record(
            AuditEvent(
                event_type=AuditEventType.USER_REGISTERED,
                user_id=user.id_,
                occurred_at=now,
            )
        )
        return CreateUserResult(user_id=user.id_)
