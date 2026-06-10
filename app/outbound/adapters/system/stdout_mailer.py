import sys
from datetime import datetime

from app.domain.value_objects.email import Email


class StdoutMailer:
    async def send_password_reset(self, to: Email, token: str, expires_at: datetime) -> None:
        print(
            f"[MAIL] password-reset to={to} token={token} expires={expires_at.isoformat()}",
            file=sys.stderr,
        )
