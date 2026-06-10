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
    return DatabaseSettings()


def load_redis_settings() -> RedisSettings:
    return RedisSettings()


def load_auth_settings() -> AuthSettings:
    return AuthSettings()  # type: ignore[call-arg]


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
