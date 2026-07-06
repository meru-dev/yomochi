from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Sent on every response regardless of protocol.
_ALWAYS: dict[str, str] = {
    "X-Frame-Options": "SAMEORIGIN",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Legacy XSS filter — harmless on modern browsers, still helps IE/older Chrome.
    "X-XSS-Protection": "1; mode=block",
    # Deny access to sensitive device APIs we never use.
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=()",
    # Prevents cross-origin window hijacking (relevant when OAuth popups are used).
    "Cross-Origin-Opener-Policy": "same-origin",
    # Lock cross-origin embedding/resource access. This is a JSON API; no
    # legitimate caller needs to <img src=...> our endpoints.
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}

# Sent only when the request arrived over HTTPS (proxied or direct).
# Prevents HSTS from locking out local dev over plain HTTP.
_HTTPS_ONLY: dict[str, str] = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

# Locked-down CSP for the JSON API surface. The frontend is a separate Next.js
# app that ships its own (looser) CSP — these headers govern only the API
# responses + their error pages.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# Swagger UI / ReDoc load inline scripts + CDN assets; applying _API_CSP to
# them breaks the docs UI entirely. We skip CSP (only) for these paths.
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_https = _is_https(scope)
        send_csp = scope.get("path") not in _DOCS_PATHS

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for header, value in _ALWAYS.items():
                    headers[header] = value
                if send_csp:
                    headers["Content-Security-Policy"] = _API_CSP
                if is_https:
                    for header, value in _HTTPS_ONLY.items():
                        headers[header] = value
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _is_https(scope: Scope) -> bool:
    if scope.get("scheme") == "https":
        return True
    for name, value in scope.get("headers", ()):
        if name == b"x-forwarded-proto" and value.lower() == b"https":
            return True
    return False
