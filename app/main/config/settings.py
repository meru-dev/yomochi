from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = SettingsConfigDict(
    env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
)


class AppSettings(BaseSettings):
    model_config = _ENV
    app_name: str = "yomochi"
    debug: bool = False
    hasher_thread_pool_size: int = 8
    # Rate limit proxy trust — comma-separated CIDRs/IPs.
    # When empty, the middleware uses scope["client"][0] verbatim (safe local default).
    # In production behind a LB, set e.g. "10.0.0.0/8,127.0.0.1".
    trusted_proxies: str = ""
    # Enable per-endpoint rate limiting. Defaults on; tests that exercise flows
    # not concerned with throttling (e.g. auth smoke tests) disable it.
    rate_limit_enabled: bool = True
    # CORS — comma-separated exact origins (e.g. "https://app.example.com,http://localhost:3000").
    # Empty (default) = middleware is not added at all; same-origin setups are unaffected.
    # Must be an explicit allow-list because allow_credentials=True forbids wildcard origins.
    cors_allow_origins: str = ""

    # SMTP — password-reset email delivery.
    # smtp_host empty (default) = SMTP disabled; the mailer provider falls back to
    # StdoutMailer. Works against any SMTP relay (SES/Resend/Gmail/...).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    # Sender address. Required when smtp_host is set (enforced at startup in providers.py).
    smtp_from_email: str = ""
    # STARTTLS on port 587 (the common case). Set False for port 465 implicit-TLS relays.
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = 10.0

    @property
    def cors_allow_origin_list(self) -> tuple[str, ...]:
        return tuple(o.strip() for o in self.cors_allow_origins.split(",") if o.strip())


class DatabaseSettings(BaseSettings):
    model_config = _ENV
    # No default: missing DATABASE_URL must fail at startup rather than
    # silently connecting to a hardcoded localhost with embedded credentials.
    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800
    db_use_null_pool: bool = False


class RedisSettings(BaseSettings):
    model_config = _ENV
    redis_url: str = "redis://localhost:6379/0"
    search_cache_ttl_seconds: int = 3600  # M5


class AuthSettings(BaseSettings):
    model_config = _ENV
    # JWT. No default: must be set via JWT_SECRET env var.
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    # Comma-separated extra HS256 keys accepted at decode time (rotation window).
    # Each key must satisfy the same ≥32-byte minimum as jwt_secret.
    jwt_verification_keys: str = ""
    session_expire_minutes: int = 60 * 24 * 30  # 30 days
    # Cookie
    cookie_name: str = "auth"
    cookie_httponly: bool = True
    cookie_secure: bool = False  # must be True in production (enforced at app startup in loader.py)
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_path: str = "/"

    @property
    def jwt_verification_key_list(self) -> tuple[str, ...]:
        return tuple(k.strip() for k in self.jwt_verification_keys.split(",") if k.strip())

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> Self:
        if not self.jwt_secret:
            msg = "JWT_SECRET must be set (non-empty)."
            raise ValueError(msg)
        if len(self.jwt_secret.encode()) < 32:
            msg = "JWT_SECRET must be at least 32 bytes (RFC 7518 §3.2). Generate: openssl rand -hex 32"
            raise ValueError(msg)
        for k in self.jwt_verification_key_list:
            if len(k.encode()) < 32:
                msg = "Each JWT_VERIFICATION_KEYS entry must be at least 32 bytes."
                raise ValueError(msg)
        return self


class OpenAISettings(BaseSettings):
    model_config = _ENV
    openai_api_key: str = ""
    openai_model_chat: str = "gpt-4o-mini"
    # HTTP transport
    openai_max_connections: int = 20
    openai_max_keepalive_connections: int = 10
    openai_connect_timeout_seconds: float = 5.0
    openai_read_timeout_chat_seconds: float = 60.0
    openai_max_retries: int = 3  # SDK auto-retry on 429/5xx with Retry-After honored
    # Per-endpoint-class rate-limit buckets. One AsyncLimiter per class so a
    # vision/parse burst can't starve interactive chat. Defaults PARTITION the
    # account RPM (sum ≈ 60) rather than each taking the full budget — separate
    # buckets must not over-subscribe the upstream account limit.
    openai_rpm_chat: int = 40
    openai_rpm_vision: int = 15
    openai_rpm_parse: int = 5
    # Bounded waiter queue per bucket; beyond this, calls are rejected fast
    # (AIRateLimitedError) instead of piling up unboundedly.
    openai_limiter_max_queue: int = 64

    @property
    def openai_rpm_per_endpoint(self) -> dict[str, int]:
        return {
            "chat": self.openai_rpm_chat,
            "vision": self.openai_rpm_vision,
            "parse": self.openai_rpm_parse,
        }

    # Circuit breaker
    openai_circuit_fail_max: int = 5
    openai_circuit_reset_seconds: int = 60


class KafkaSettings(BaseSettings):
    model_config = _ENV
    kafka_bootstrap_servers: str = "localhost:9092"
    # Topics — M3
    kafka_topic_insights: str = "yomochi.insights.v1"
    kafka_topic_dlq: str = "yomochi.dlq.v1"
    # Outbox worker — M3
    outbox_poll_interval_seconds: int = 5
    outbox_batch_size: int = 100
    outbox_max_retries: int = 5
    # Consumer idempotency / DLQ — M3
    consumer_idempotency_ttl_seconds: int = 86400  # 24 h
    consumer_max_retries: int = 3


class ObservabilitySettings(BaseSettings):
    model_config = _ENV
    log_format: Literal["json", "console"] = "console"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "yomochi-api"
    otel_enabled: bool = True


class ChatSettings(BaseSettings):
    model_config = _ENV
    # Per-user daily token cap (prompt + completion). Tracks runaway cost
    # from injection loops, scrapers, credential theft.
    chat_daily_token_limit: int = 100_000
    # Max OpenAI tool-selection round-trips before forcing a final answer.
    # Bounds latency/cost in tools mode.
    chat_max_tool_iterations: int = 3


class IngestionSettings(BaseSettings):
    model_config = _ENV
    ingestion_max_upload_size_mb: int = 5
    ingestion_image_processing_concurrency: int = 3
    ingestion_vision_model: str = "gpt-4o-mini"
    ingestion_max_image_dimension: int = 1568
    ingestion_jpeg_quality: int = 85
    ingestion_vision_timeout_seconds: float = 45.0


class InsightWorkerSettings(BaseSettings):
    model_config = _ENV
    min_transactions_for_insight: int = 3
    reaper_lease_minutes: int = 15
    reaper_max_retries: int = 3
    reaper_interval_minutes: int = 10
