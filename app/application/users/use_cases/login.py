from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.common.audit_event import AuditEvent
from app.application.common.ports.audit_log import AuditLog
from app.application.users.ports.session_store import SessionStore
from app.application.users.ports.user_repository import UserRepository
from app.application.users.session import Session
from app.domain.ports.id_generator import SessionIdGenerator
from app.domain.ports.password_hasher import PasswordHasher
from app.domain.value_objects.email import Email
from app.domain.value_objects.enums import AuditEventType
from app.domain.value_objects.password import RawPassword, UserPasswordHash


class InvalidCredentialsError(Exception):
    pass


# Precomputed bcrypt-12 hash of an arbitrary constant password.
# Used on the user-not-found path to make timing indistinguishable from
# the real verify path (~250 ms bcrypt-12 work factor), preventing
# user-enumeration via response-time oracle.  Do NOT recompute at import time.
_DUMMY_HASH = UserPasswordHash("$2b$12$FzSGbDqRa0dL0WzZiCQivuY.jetzzuJc1tFFi2JWBwMVVPjQOxtEG")


@dataclass(frozen=True, slots=True)
class LoginCommand:
    email: str
    raw_password: str
    user_agent: str
    ip: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    session: Session


class LoginUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        password_hasher: PasswordHasher,
        session_store: SessionStore,
        session_id_generator: SessionIdGenerator,
        audit_log: AuditLog,
        session_ttl: timedelta,
    ) -> None:
        self._user_repo = user_repo
        self._password_hasher = password_hasher
        self._session_store = session_store
        self._session_id_generator = session_id_generator
        self._audit_log = audit_log
        self._session_ttl = session_ttl

    async def __call__(self, command: LoginCommand) -> LoginResult:
        email = Email(command.email)
        user = await self._user_repo.get_by_email(email)
        raw_password = RawPassword(command.raw_password)
        if user is None:
            # Constant-time dummy verify to prevent timing-oracle enumeration.
            await self._password_hasher.verify(raw_password, _DUMMY_HASH)
            raise InvalidCredentialsError()

        if not await self._password_hasher.verify(raw_password, user.password_hash):
            raise InvalidCredentialsError()

        now = datetime.now(UTC)
        session = Session(
            id_=self._session_id_generator(),
            user_id=user.id_,
            expires_at=now + self._session_ttl,
            user_agent=command.user_agent,
            ip=command.ip,
        )
        await self._session_store.save(session)
        await self._audit_log.record(
            AuditEvent(
                event_type=AuditEventType.USER_LOGIN,
                user_id=user.id_,
                occurred_at=now,
                ip=command.ip,
                user_agent=command.user_agent,
            )
        )
        return LoginResult(session=session)
