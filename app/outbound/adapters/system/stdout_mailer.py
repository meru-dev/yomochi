from datetime import datetime

import structlog

from app.domain.value_objects.email import Email

logger = structlog.get_logger(__name__)


class StdoutMailer:
    async def send_password_reset(self, to: Email, token: str, expires_at: datetime) -> None:
        logger.info(
            "stdout_mailer_send_password_reset",
            to=str(to),
            token=token,
            expires_at=expires_at.isoformat(),
        )
