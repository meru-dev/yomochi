from dataclasses import dataclass
from typing import Literal

Scope = Literal["user", "ip"]


@dataclass(frozen=True)
class Policy:
    rate_per_minute: int
    burst: int  # extra requests allowed above the steady rate, in a burst
    scope: Scope  # "user" prefers the session cookie; falls back to IP for anon


# Order matters — first prefix match wins.
POLICIES: tuple[tuple[str, Policy], ...] = (
    ("/v1/auth/login", Policy(rate_per_minute=5, burst=2, scope="ip")),
    ("/v1/auth/register", Policy(rate_per_minute=3, burst=1, scope="ip")),
    ("/v1/auth/password-reset/start", Policy(rate_per_minute=3, burst=1, scope="ip")),
    ("/v1/chat/stream", Policy(rate_per_minute=20, burst=5, scope="user")),
    ("/v1/chat", Policy(rate_per_minute=20, burst=5, scope="user")),
    ("/v1/insights/requests", Policy(rate_per_minute=10, burst=3, scope="user")),
    ("/v1/ingestion/receipts", Policy(rate_per_minute=10, burst=2, scope="user")),
)

DEFAULT = Policy(rate_per_minute=120, burst=30, scope="user")

# Endpoints that bypass rate limiting entirely.
SKIP: frozenset[str] = frozenset(
    {"/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"}
)


def resolve_policy(path: str) -> Policy:
    """First-prefix-match wins; falls back to DEFAULT."""
    for prefix, policy in POLICIES:
        if path.startswith(prefix):
            return policy
    return DEFAULT


def policy_marker(policy: Policy) -> str:
    """Stable per-policy suffix so different limits don't share GCRA state."""
    return f"{policy.rate_per_minute}_{policy.burst}"
