from app.main.config.settings import (
    AppSettings,
    AuthSettings,
    ChatSettings,
    DatabaseSettings,
    IngestionSettings,
    InsightWorkerSettings,
    KafkaSettings,
    ObservabilitySettings,
    OpenAISettings,
    RedisSettings,
)


def load_app_settings() -> AppSettings:
    return AppSettings()


def load_database_settings() -> DatabaseSettings:
    return DatabaseSettings()  # type: ignore[call-arg]


def load_redis_settings() -> RedisSettings:
    return RedisSettings()


def load_auth_settings() -> AuthSettings:
    return AuthSettings()  # type: ignore[call-arg]


def enforce_cookie_secure(app_settings: AppSettings, auth_settings: AuthSettings) -> None:
    """Raise at startup when running non-debug with cookie_secure=False.

    AuthSettings cannot see AppSettings.debug (separate Pydantic models), so
    the cross-setting invariant is enforced here at the composition boundary.
    """
    if not app_settings.debug and not auth_settings.cookie_secure:
        raise RuntimeError(
            "COOKIE_SECURE must be True in production (debug=False). "
            "Set COOKIE_SECURE=true in the environment or enable DEBUG=true for local dev."
        )


def load_openai_settings() -> OpenAISettings:
    return OpenAISettings()


def load_kafka_settings() -> KafkaSettings:
    return KafkaSettings()


def load_ingestion_settings() -> IngestionSettings:
    return IngestionSettings()


def load_observability_settings() -> ObservabilitySettings:
    return ObservabilitySettings()


def load_chat_settings() -> ChatSettings:
    return ChatSettings()


def load_insight_worker_settings() -> InsightWorkerSettings:
    return InsightWorkerSettings()
