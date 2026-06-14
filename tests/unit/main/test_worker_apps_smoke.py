from __future__ import annotations

import pytest
from faststream import FastStream

from app.main.config.settings import (
    DatabaseSettings,
    KafkaSettings,
    ObservabilitySettings,
    OpenAISettings,
    RedisSettings,
)
from app.main.insight import main as insight_main
from app.main.portrait import main as portrait_main
from app.main.transaction import main as transaction_main


@pytest.fixture
def db_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_url="postgresql+asyncpg://yomochi:yomochi@localhost:5432/yomochi", _env_file=None
    )


@pytest.fixture
def redis_settings() -> RedisSettings:
    return RedisSettings(_env_file=None)


@pytest.fixture
def kafka_settings() -> KafkaSettings:
    return KafkaSettings(_env_file=None)


@pytest.fixture
def openai_settings() -> OpenAISettings:
    return OpenAISettings(_env_file=None)


@pytest.fixture
def obs_settings() -> ObservabilitySettings:
    # metrics_enabled=False — workers would otherwise try to bind port 9090,
    # which collides with whatever's already running (compose prometheus,
    # another worker smoke test in the same process, etc.)
    return ObservabilitySettings(
        _env_file=None,
        otel_enabled=False,
        log_format="console",
        metrics_enabled=False,
    )


def test_transaction_worker_app_constructs(
    db_settings: DatabaseSettings,
    redis_settings: RedisSettings,
    kafka_settings: KafkaSettings,
    obs_settings: ObservabilitySettings,
) -> None:
    app = transaction_main.make_app(
        db_settings=db_settings,
        redis_settings=redis_settings,
        kafka_settings=kafka_settings,
        obs_settings=obs_settings,
    )
    assert isinstance(app, FastStream)


def test_insight_worker_app_constructs(
    db_settings: DatabaseSettings,
    redis_settings: RedisSettings,
    kafka_settings: KafkaSettings,
    openai_settings: OpenAISettings,
    obs_settings: ObservabilitySettings,
) -> None:
    app = insight_main.make_app(
        db_settings=db_settings,
        redis_settings=redis_settings,
        kafka_settings=kafka_settings,
        openai_settings=openai_settings,
        obs_settings=obs_settings,
    )
    assert isinstance(app, FastStream)


def test_portrait_worker_modules_importable() -> None:
    """Portrait worker has no FastStream app — only an asyncio loop entry.

    We assert the public surface exists; constructing the Dishka container
    is covered by `test_worker_providers_isolation.py`.
    """
    assert callable(portrait_main.run)
    assert callable(portrait_main.main)
    assert callable(portrait_main._portrait_refresh_loop)
