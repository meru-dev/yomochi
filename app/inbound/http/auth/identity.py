from app.application.common.ports.identity_context import IdentityContext
from app.application.users.ports.session_store import SessionStore
from app.application.users.ports.token_decoder import TokenDecoder
from app.domain.value_objects.ids import SessionId, UserId
from app.inbound.http.auth.cookie_manager import CookieManager


class UnauthenticatedError(Exception):
    pass


class _JwtIdentity:
    def __init__(self, user_id: UserId, session_id: SessionId) -> None:
        self._user_id = user_id
        self._session_id = session_id

    @property
    def user_id(self) -> UserId:
        return self._user_id

    @property
    def session_id(self) -> SessionId:
        return self._session_id


async def resolve_identity(
    cookie_manager: CookieManager,
    decoder: TokenDecoder,
    session_store: SessionStore,
) -> IdentityContext:
    token = cookie_manager.read()
    if token is None:
        raise UnauthenticatedError
    result = decoder.decode(token)
    if result is None:
        raise UnauthenticatedError
    user_id, session_id = result
    session = await session_store.get(session_id, user_id)
    if session is None:
        raise UnauthenticatedError
    return _JwtIdentity(user_id, session_id)
