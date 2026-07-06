import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEADER = "X-Request-ID"
_HEADER_LOWER = b"x-request-id"


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _read_header(scope) or str(uuid.uuid4())

        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _read_header(scope: Scope) -> str | None:
    for name, value in scope.get("headers", ()):
        if name == _HEADER_LOWER:
            try:
                decoded: str = value.decode("latin-1")
            except UnicodeDecodeError:
                return None
            return decoded
    return None
