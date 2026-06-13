from dataclasses import dataclass
from typing import Literal

Scope = Literal["user", "ip"]


@dataclass(frozen=True)
class Policy:
    rate_per_minute: int
    burst: int  # extra requests allowed above the steady rate, in a burst
    scope: Scope  # "user" prefers the session cookie; falls back to IP for anon


# Order matters — first match wins.
# Each entry is (method, path_prefix, policy).
# An empty method string ("") matches any HTTP method.
POLICIES: tuple[tuple[str, str, Policy], ...] = (
    ("", "/api/v1/auth/login", Policy(rate_per_minute=5, burst=2, scope="ip")),
    ("", "/api/v1/auth/register", Policy(rate_per_minute=3, burst=1, scope="ip")),
    ("", "/api/v1/auth/password-reset/", Policy(rate_per_minute=3, burst=1, scope="ip")),
    ("POST", "/api/v1/chat/stream", Policy(rate_per_minute=20, burst=5, scope="user")),
    ("POST", "/api/v1/chat", Policy(rate_per_minute=20, burst=5, scope="user")),
    ("", "/api/v1/insights/requests", Policy(rate_per_minute=10, burst=3, scope="user")),
    ("POST", "/api/v1/ingestion/parse-receipt", Policy(rate_per_minute=10, burst=2, scope="user")),
)

DEFAULT = Policy(rate_per_minute=120, burst=30, scope="user")

# Endpoints that bypass rate limiting entirely.
SKIP: frozenset[str] = frozenset(
    {"/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"}
)


def resolve_policy(path: str, method: str = "") -> Policy:
    """First match wins; falls back to DEFAULT.

    Entries with a non-empty method only match requests with that HTTP method.
    Entries with an empty method match any HTTP method.
    """
    for entry_method, prefix, policy in POLICIES:
        if path.startswith(prefix) and (not entry_method or entry_method == method.upper()):
            return policy
    return DEFAULT


def policy_marker(policy: Policy) -> str:
    """Stable per-policy suffix so different limits don't share GCRA state."""
    return f"{policy.rate_per_minute}_{policy.burst}"
