import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.application.users.audit_event import AuditEvent
from app.application.users.password_reset_token import PasswordResetToken
from app.application.users.ports.audit_log import AuditLog
from app.application.users.ports.mailer import Mailer
from app.application.users.ports.password_reset_token_store import PasswordResetTokenStore
from app.application.users.ports.user_repository import UserRepository
from app.domain.ports.id_generator import PasswordResetTokenIdGenerator
from app.domain.value_objects.email import Email
from app.domain.value_objects.enums import AuditEventType

_TOKEN_TTL = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class StartPasswordResetCommand:
    email: str


class StartPasswordResetUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        token_store: PasswordResetTokenStore,
        token_id_generator: PasswordResetTokenIdGenerator,
        mailer: Mailer,
        audit_log: AuditLog,
    ) -> None:
        self._user_repo = user_repo
        self._token_store = token_store
        self._token_id_generator = token_id_generator
        self._mailer = mailer
        self._audit_log = audit_log

    async def __call__(self, command: StartPasswordResetCommand) -> None:
        email = Email(command.email)
        user = await self._user_repo.get_by_email(email)
        if user is None:
            return

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = datetime.now(UTC)
        expires_at = now + _TOKEN_TTL

        token = PasswordResetToken(
            id_=self._token_id_generator(),
            user_id=user.id_,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await self._token_store.save(token)
        await self._mailer.send_password_reset(email, raw_token, expires_at)
        await self._audit_log.record(
            AuditEvent(
                event_type=AuditEventType.PASSWORD_RESET_REQUESTED,
                user_id=user.id_,
                occurred_at=now,
            )
        )
