import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.responses import JSONResponse, ORJSONResponse
from fastapi.routing import APIRoute
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.inbound.http.auth.middleware import AuthCookieMiddleware
from app.inbound.http.errors.handlers import register_exception_handlers
from app.inbound.http.middleware.idempotency import IdempotencyMiddleware
from app.inbound.http.middleware.rate_limit import RateLimitMiddleware, parse_trusted_proxies
from app.inbound.http.middleware.request_id import RequestIdMiddleware
from app.inbound.http.middleware.security_headers import SecurityHeadersMiddleware
from app.inbound.http.router import make_api_router
from app.main.config.loader import (
    enforce_cookie_secure,
    load_app_settings,
    load_auth_settings,
    load_chat_settings,
    load_database_settings,
    load_ingestion_settings,
    load_insight_worker_settings,
    load_observability_settings,
    load_openai_settings,
    load_redis_settings,
)
from app.main.config.settings import (
    AppSettings,
    AuthSettings,
    ChatSettings,
    DatabaseSettings,
    IngestionSettings,
    InsightWorkerSettings,
    ObservabilitySettings,
    OpenAISettings,
    RedisSettings,
)
from app.main.ioc import all_providers
from app.main.logging import configure_logging
from app.outbound.observability.otel import configure_otel
from app.outbound.observability.prometheus import (
    REGISTRY,
    http_request_duration_metric,
    http_requests_metric,
)
from app.outbound.persistence_sqla.mappings.all import map_tables

log = structlog.get_logger(__name__)


def _stable_operation_id(route: APIRoute) -> str:
    """Generate stable, predictable operationIds for OpenAPI / TS codegen.

    FastAPI's default appends the full module path which produces unwieldy
    names and changes when files move. We use `<tag>_<route.name>` when a
    tag is present, falling back to just the function name otherwise.
    Tag names are slugified (spaces -> underscores, lowercased) so the
    resulting IDs are valid JS identifiers.
    """
    if route.tags:
        tag = route.tags[0]
        tag_str = tag.value if hasattr(tag, "value") else str(tag)
        tag_slug = tag_str.lower().replace(" ", "_")
        return f"{tag_slug}_{route.name}"
    return route.name


def make_app(
    app_settings: AppSettings | None = None,
    database_settings: DatabaseSettings | None = None,
    redis_settings: RedisSettings | None = None,
    auth_settings: AuthSettings | None = None,
    openai_settings: OpenAISettings | None = None,
    observability_settings: ObservabilitySettings | None = None,
    ingestion_settings: IngestionSettings | None = None,
    chat_settings: ChatSettings | None = None,
    insight_worker_settings: InsightWorkerSettings | None = None,
) -> FastAPI:
    app_cfg = app_settings or load_app_settings()
    db_cfg = database_settings or load_database_settings()
    redis_cfg = redis_settings or load_redis_settings()
    auth_cfg = auth_settings or load_auth_settings()
    openai_cfg = openai_settings or load_openai_settings()
    obs_cfg = observability_settings or load_observability_settings()
    ingestion_cfg = ingestion_settings or load_ingestion_settings()
    chat_cfg = chat_settings or load_chat_settings()
    insight_worker_cfg = insight_worker_settings or load_insight_worker_settings()

    enforce_cookie_secure(app_cfg, auth_cfg)
    configure_logging(log_format=obs_cfg.log_format, debug=app_cfg.debug)
    configure_otel(
        service_name=obs_cfg.otel_service_name,
        otlp_endpoint=obs_cfg.otel_exporter_otlp_endpoint,
        enabled=obs_cfg.otel_enabled,
    )
    map_tables()

    redis: Redis = Redis.from_url(  # type: ignore[type-arg]
        redis_cfg.redis_url,
        decode_responses=False,
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
        health_check_interval=30,
    )
    container = make_async_container(
        *all_providers(),
        context={
            AppSettings: app_cfg,
            DatabaseSettings: db_cfg,
            RedisSettings: redis_cfg,
            AuthSettings: auth_cfg,
            OpenAISettings: openai_cfg,
            IngestionSettings: ingestion_cfg,
            ChatSettings: chat_cfg,
            InsightWorkerSettings: insight_worker_cfg,
            Redis: redis,
        },
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        log.info("startup", service=app_cfg.app_name)
        if obs_cfg.otel_enabled:
            # SQLAlchemy needs the engine instance (created lazily by the
            # container), so instrument it here once it is resolvable.
            engine = await container.get(AsyncEngine)
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        yield
        log.info("shutdown", service=app_cfg.app_name)
        await container.close()
        with contextlib.suppress(Exception):
            await redis.aclose()  # type: ignore[attr-defined]

    app = FastAPI(
        title="Yomochi",
        description="AI-powered expense understanding",
        version="0.1.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        redirect_slashes=False,
        generate_unique_id_function=_stable_operation_id,
    )

    setup_dishka(container, app)
    register_exception_handlers(app)

    if obs_cfg.otel_enabled:
        FastAPIInstrumentor.instrument_app(app)
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        # Prometheus instrumentation — replaces the legacy HttpMetricsMiddleware.
        # prometheus-fastapi-instrumentator hooks at the Starlette router level
        # which gives accurate templated handlers and proper status codes even
        # for 404s and exceptions. Client disconnects (no response) are emitted
        # with status_class="499" by http_requests_metric (see prometheus.py) —
        # so we don't need a parallel custom middleware just for that case.
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=False,
            should_group_untemplated=True,
            excluded_handlers=["/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"],
            inprogress_name="http_requests_inprogress",
            inprogress_labels=True,
            registry=REGISTRY,
        ).add(http_requests_metric()).add(http_request_duration_metric()).instrument(app).expose(
            app, include_in_schema=False, endpoint="/metrics", tags=["ops"]
        )

    # Middlewares — registered last = outermost wrapper
    app.add_middleware(
        AuthCookieMiddleware,
        cookie_name=auth_cfg.cookie_name,
        cookie_path=auth_cfg.cookie_path,
        cookie_httponly=auth_cfg.cookie_httponly,
        cookie_secure=auth_cfg.cookie_secure,
        cookie_samesite=auth_cfg.cookie_samesite,
    )
    app.add_middleware(IdempotencyMiddleware, redis=redis, cookie_name=auth_cfg.cookie_name)
    if app_cfg.rate_limit_enabled:
        trusted_proxies = parse_trusted_proxies(app_cfg.trusted_proxies)
        app.add_middleware(
            RateLimitMiddleware,
            redis=redis,
            trusted_proxies=trusted_proxies,
            cookie_name=auth_cfg.cookie_name,
        )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)  # outermost — runs first, echoes/generates X-Request-ID

    app.state.readiness_container = container
    app.state.readiness_redis = redis
    _register_routes(app)
    return app


async def _check_postgres(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis(redis: "Redis[bytes]") -> None:
    await redis.ping()


def _register_routes(app: FastAPI) -> None:
    # /metrics is mounted by Instrumentator.expose() above.
    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"])
    async def ready() -> Any:
        container = app.state.readiness_container
        redis_client: Redis[bytes] = app.state.readiness_redis
        checks: dict[str, str] = {"postgres": "ok", "redis": "ok"}
        ok = True

        try:
            engine = await container.get(AsyncEngine)
            await asyncio.wait_for(_check_postgres(engine), timeout=2.0)
        except Exception as exc:
            ok = False
            checks["postgres"] = f"error: {type(exc).__name__}"

        try:
            await asyncio.wait_for(_check_redis(redis_client), timeout=1.0)
        except Exception as exc:
            ok = False
            checks["redis"] = f"error: {type(exc).__name__}"

        if not ok:
            return JSONResponse(
                {"status": "not_ready", "checks": checks},
                status_code=503,
            )
        return {"status": "ok", "checks": checks}

    app.include_router(make_api_router())
