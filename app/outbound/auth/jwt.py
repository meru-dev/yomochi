from collections.abc import Sequence
from uuid import UUID

import jwt

from app.application.users.session import Session
from app.domain.value_objects.ids import SessionId, UserId


class JwtCodec:
    SESSION_ID_CLAIM = "sid"
    USER_ID_CLAIM = "uid"
    EXPIRATION_CLAIM = "exp"

    def __init__(
        self,
        signing_key: str,
        algorithm: str,
        verification_keys: Sequence[str] = (),
    ) -> None:
        self._signing_key = signing_key
        self._algorithm = algorithm
        self._verification_keys: tuple[str, ...] = (signing_key, *tuple(verification_keys))

    def encode(self, session: Session) -> str:
        payload = {
            self.SESSION_ID_CLAIM: str(session.id_),
            self.USER_ID_CLAIM: str(session.user_id),
            self.EXPIRATION_CLAIM: session.expires_at,
        }
        return jwt.encode(payload, self._signing_key, algorithm=self._algorithm)

    def decode(self, token: str) -> tuple[UserId, SessionId] | None:
        payload = None
        for key in self._verification_keys:
            try:
                payload = jwt.decode(
                    token,
                    key,
                    algorithms=[self._algorithm],
                    options={
                        "require": [
                            self.SESSION_ID_CLAIM,
                            self.USER_ID_CLAIM,
                            self.EXPIRATION_CLAIM,
                        ]
                    },
                )
                break
            except jwt.InvalidSignatureError:
                continue
            except jwt.PyJWTError:
                return None

        if payload is None:
            return None

        try:
            user_id = UserId(UUID(payload[self.USER_ID_CLAIM]))
            session_id = SessionId(UUID(payload[self.SESSION_ID_CLAIM]))
        except (ValueError, KeyError):
            return None

        return user_id, session_id
