from collections.abc import Callable
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, make_asgi_app
from prometheus_fastapi_instrumentator.metrics import Info

REGISTRY = CollectorRegistry(auto_describe=True)


def make_metrics_app() -> Any:
    """Return a Prometheus metrics ASGI app for mounting at /metrics."""
    return make_asgi_app(registry=REGISTRY)


# Outbox relay — M3
outbox_pending_total = Gauge(
    "outbox_pending_events",
    "Number of PENDING rows in outbox_events",
    registry=REGISTRY,
)

outbox_relay_total = Counter(
    "outbox_relay_total",
    "Outbox relay attempts",
    labelnames=["status"],  # sent | failed
    registry=REGISTRY,
)

# Consumer side — M3
consumer_idempotency_skips_total = Counter(
    "consumer_idempotency_skips_total",
    "Events skipped by consumer idempotency check",
    labelnames=["topic"],
    registry=REGISTRY,
)

consumer_dlq_events_total = Counter(
    "consumer_dlq_events_total",
    "Events parked in DLQ after max retries",
    labelnames=["topic"],
    registry=REGISTRY,
)

# Insights — M4
insight_fallback_total = Counter(
    "insight_fallback_total",
    "Insight generations served by the deterministic fallback after a primary "
    "LLM-provider failure (F2)",
    labelnames=["reason"],  # rate_limited | timeout | unavailable | invalid_request | error
    registry=REGISTRY,
)

insight_generation_duration_seconds = Histogram(
    "insight_generation_duration_seconds",
    "End-to-end insight generation duration",
    labelnames=["context_quality"],  # full | partial | none
    buckets=[0.5, 1, 2, 5, 10, 20, 30, 60],
    registry=REGISTRY,
)

openai_call_total = Counter(
    "openai_call_total",
    "OpenAI API calls",
    # outcome: success | rate_limited | timeout | unavailable | invalid_request | error
    labelnames=["endpoint", "outcome"],
    registry=REGISTRY,
)

openai_call_duration_seconds = Histogram(
    "openai_call_duration_seconds",
    "OpenAI API call latency",
    labelnames=["endpoint"],
    buckets=[0.1, 0.25, 0.5, 1, 2, 5, 10, 20],
    registry=REGISTRY,
)

openai_tokens_total = Counter(
    "openai_tokens_total",
    "OpenAI tokens consumed",
    labelnames=["endpoint", "direction"],  # direction: prompt|completion|total
    registry=REGISTRY,
)

openai_circuit_state = Gauge(
    "openai_circuit_state",
    "OpenAI circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN)",
    registry=REGISTRY,
)

openai_limiter_waiting = Gauge(
    "openai_limiter_waiting",
    "Coroutines waiting on the OpenAI rate limiter (token bucket)",
    labelnames=["endpoint"],  # chat | vision | parse
    registry=REGISTRY,
)

openai_limiter_rejected_total = Counter(
    "openai_limiter_rejected_total",
    "OpenAI calls rejected because the per-endpoint limiter waiter queue was full (F19)",
    labelnames=["endpoint"],  # chat | vision | parse
    registry=REGISTRY,
)

openai_cost_usd_total = Counter(
    "openai_cost_usd_total",
    "Estimated OpenAI API cost in USD",
    labelnames=["endpoint", "model"],
    registry=REGISTRY,
)

# Prompt-caching (F1) — cached_tokens is the subset of prompt_tokens served from
# OpenAI's automatic prompt cache (≥1024-token stable prefix). Cache-hit rate =
# openai_cached_tokens_total / openai_tokens_total{direction="prompt"}.
openai_cached_tokens_total = Counter(
    "openai_cached_tokens_total",
    "OpenAI prompt tokens served from the prompt cache (cache hits)",
    labelnames=["endpoint", "model"],
    registry=REGISTRY,
)

quota_blocked_total = Counter(
    "quota_blocked_total",
    "Quota enforcement blocks",
    labelnames=["resource", "plan"],
    registry=REGISTRY,
)

search_cache_hits_total = Counter(
    "search_cache_hits_total",
    "Redis search cache hits",
    registry=REGISTRY,
)

search_cache_misses_total = Counter(
    "search_cache_misses_total",
    "Redis search cache misses",
    registry=REGISTRY,
)

# Rate limiter — fail-open Redis error counter
rate_limit_redis_error_total = Counter(
    "rate_limit_redis_error_total",
    "Rate limit Redis errors (middleware fails open on these)",
    registry=REGISTRY,
)

# HTTP — inbound request metrics.
#
# Recorded by prometheus-fastapi-instrumentator hooks (see app_factory.py).
# We register custom closures rather than the library's defaults so we can
# preserve the historical label schema (method, route, status_class) that the
# Grafana dashboards + Prometheus alert rules in deploy/observability/ depend
# on. The instrumentator's default closures use `handler` and `status`, which
# would silently break those queries.
http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests by method, route template, status class, and route class",
    labelnames=["method", "route", "status_class", "route_class"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "route", "route_class"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
    registry=REGISTRY,
)

# Routes that call an LLM at request time or dispatch work to an LLM worker.
_AI_ROUTE_PREFIXES = (
    "/api/v1/chat",
    "/api/v1/insights",
    "/api/v1/ingestion",
)
_AI_ROUTE_EXACT = {"/api/v1/transactions/parse-text"}


def _classify_route(route: str) -> str:
    if route in _AI_ROUTE_EXACT or any(route.startswith(p) for p in _AI_ROUTE_PREFIXES):
        return "ai"
    return "standard"


def http_requests_metric() -> Callable[[Info], None]:
    """Instrumentator closure for the request counter.

    Detects client disconnects (no response object produced) and labels them
    as ``499`` status_class, mirroring nginx's convention. This replaces the
    custom HttpMetricsMiddleware that used to live in app/inbound/http/middleware.
    """

    def instrumentation(info: Info) -> None:
        route = info.modified_handler or "unknown"
        if info.response is None:
            status_class = "499"
        else:
            status = info.modified_status  # e.g. "2xx" when grouped
            status_class = status if status.endswith("xx") else f"{status[0]}xx"
        http_requests_total.labels(info.method, route, status_class, _classify_route(route)).inc()

    return instrumentation


def http_request_duration_metric() -> Callable[[Info], None]:
    """Instrumentator closure for the request duration histogram."""

    def instrumentation(info: Info) -> None:
        route = info.modified_handler or "unknown"
        http_request_duration_seconds.labels(info.method, route, _classify_route(route)).observe(
            info.modified_duration
        )

    return instrumentation
