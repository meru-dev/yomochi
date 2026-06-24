from datetime import datetime
from email.message import EmailMessage

import aiosmtplib
import structlog

from app.domain.value_objects.email import Email

logger = structlog.get_logger(__name__)

_SUBJECT = "Reset your Yomochi password"


class SmtpMailer:
    """Delivers password-reset emails over SMTP via aiosmtplib.

    Provider-agnostic: works against SES, Resend, Gmail, or any SMTP relay.
    There is no frontend reset-URL base in this repo, so the email body carries
    the raw token and expiry (mirroring StdoutMailer); a clickable link is a
    separate future feature.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_starttls: bool,
        timeout: float,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._use_starttls = use_starttls
        self._timeout = timeout

    async def send_password_reset(self, to: Email, token: str, expires_at: datetime) -> None:
        message = EmailMessage()
        message["From"] = self._from_email
        message["To"] = str(to)
        message["Subject"] = _SUBJECT
        message.set_content(
            "You requested a password reset for your Yomochi account.\n\n"
            f"Reset token: {token}\n"
            f"This token expires at {expires_at.isoformat()}.\n\n"
            "If you did not request this, you can safely ignore this email.\n"
        )

        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username or None,
            password=self._password or None,
            start_tls=self._use_starttls,
            timeout=self._timeout,
        )

        # Never log the token or password.
        logger.info(
            "smtp_mailer_send_password_reset",
            to=str(to),
            expires_at=expires_at.isoformat(),
        )
