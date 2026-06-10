from typing import ClassVar, Literal

from starlette.datastructures import MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.inbound.http.auth.cookie_manager import STAGED_COOKIE


class AuthCookieMiddleware:
    """Pure ASGI middleware that emits the session ``Set-Cookie`` header.

    Controllers stage the cookie value via :class:`CookieManager`, which writes
    to ``request.state.{STAGED_COOKIE}``. After the inner app finishes we read
    the staged value back off ``scope["state"]`` and translate it into the
    appropriate ``Set-Cookie`` (or delete) header on ``http.response.start``.
    """

    MISSING: ClassVar[object] = object()

    def __init__(
        self,
        app: ASGIApp,
        *,
        cookie_name: str,
        cookie_path: str,
        cookie_httponly: bool,
        cookie_secure: bool,
        cookie_samesite: Literal["lax", "strict", "none"],
    ) -> None:
        self.app = app
        self._cookie_name = cookie_name
        self._cookie_path = cookie_path
        self._cookie_httponly = cookie_httponly
        self._cookie_secure = cookie_secure
        self._cookie_samesite = cookie_samesite

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Ensure the state dict exists so controllers can stage cookies via
        # ``request.state`` (Starlette's ``Request.state`` proxies ``scope["state"]``).
        state = scope.setdefault("state", {})

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                staged = state.get(STAGED_COOKIE, self.MISSING)
                if staged is not self.MISSING:
                    self._apply_cookie(message, staged)
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _apply_cookie(self, message: Message, staged: object) -> None:
        # We piggy-back on Starlette's Response cookie machinery to format the
        # Set-Cookie value (handles attributes + deletion correctly), then copy
        # the produced header over to the real response.
        carrier: Response = Response()
        if staged is None:
            carrier.delete_cookie(key=self._cookie_name, path=self._cookie_path)
        else:
            carrier.set_cookie(
                key=self._cookie_name,
                value=str(staged),
                path=self._cookie_path,
                httponly=self._cookie_httponly,
                secure=self._cookie_secure,
                samesite=self._cookie_samesite,
            )
        headers = MutableHeaders(scope=message)
        for key, value in carrier.headers.raw:
            if key.lower() == b"set-cookie":
                headers.append("set-cookie", value.decode("latin-1"))
