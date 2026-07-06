from dataclasses import dataclass

import httpx
import purgatory
from aiolimiter import AsyncLimiter
from openai import AsyncOpenAI

from app.outbound.adapters.openai._gateway.gateway import OpenAIGateway

# Endpoint classes with independent rate-limit + circuit-breaker buckets.
_ENDPOINTS = ("chat", "vision", "parse")


@dataclass(frozen=True)
class OpenAIGatewayConfig:
    api_key: str
    max_connections: int
    max_keepalive_connections: int
    connect_timeout_seconds: float
    read_timeout_chat_seconds: float
    max_retries: int
    rpm_per_endpoint: dict[str, int]  # one token bucket per endpoint class
    max_queue: int
    circuit_fail_max: int
    circuit_reset_seconds: int


async def build_openai_gateway(
    cfg: OpenAIGatewayConfig,
) -> tuple[OpenAIGateway, httpx.AsyncClient]:
    """Build the gateway plus the underlying httpx.AsyncClient.

    The caller owns the httpx client lifetime (close it on process shutdown).
    """
    http_client = httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=cfg.max_connections,
            max_keepalive_connections=cfg.max_keepalive_connections,
        ),
        timeout=httpx.Timeout(
            connect=cfg.connect_timeout_seconds,
            read=cfg.read_timeout_chat_seconds,
            write=10.0,
            pool=10.0,
        ),
    )
    client = AsyncOpenAI(
        api_key=cfg.api_key,
        http_client=http_client,
        max_retries=cfg.max_retries,
    )
    # One token bucket per endpoint class so a burst on one (vision/parse) can't
    # starve another (interactive chat). Falls back to a small default rpm for any
    # class missing from the config map.
    limiters = {
        endpoint: AsyncLimiter(max_rate=cfg.rpm_per_endpoint.get(endpoint, 10), time_period=60)
        for endpoint in _ENDPOINTS
    }
    factory = purgatory.AsyncCircuitBreakerFactory(
        default_threshold=cfg.circuit_fail_max,
        default_ttl=cfg.circuit_reset_seconds,
    )
    breakers = {
        endpoint: await factory.get_breaker(f"openai_{endpoint}") for endpoint in _ENDPOINTS
    }
    gateway = OpenAIGateway(
        client=client,
        limiters=limiters,
        breakers=breakers,
        default_read_timeout_seconds=cfg.read_timeout_chat_seconds,
        max_queue=cfg.max_queue,
    )
    return gateway, http_client
