from dataclasses import dataclass
from datetime import datetime

from app.domain.value_objects.ids import PasswordResetTokenId, UserId


@dataclass(frozen=True, slots=True)
class PasswordResetToken:
    id_: PasswordResetTokenId
    user_id: UserId
    token_hash: str
    expires_at: datetime
