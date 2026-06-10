import pytest
import sqlalchemy as sa
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.main.api.app_factory import make_app
from app.main.config.settings import (
    AppSettings,
    AuthSettings,
    DatabaseSettings,
    ObservabilitySettings,
    RedisSettings,
)


@pytest.fixture(scope="session")
def integration_settings(postgres_url: str, redis_url: str) -> dict:
    return {
        "app_settings": AppSettings(debug=True),
        "database_settings": DatabaseSettings(
            database_url=postgres_url,
            db_use_null_pool=True,
        ),
        "redis_settings": RedisSettings(redis_url=redis_url),
        "auth_settings": AuthSettings(
            jwt_secret="integration-test-secret-must-be-32bytes!", cookie_secure=False
        ),
        "observability_settings": ObservabilitySettings(log_format="console", otel_enabled=False),
    }


# ---------------------------------------------------------------------------
# Per-test cleanup — truncate user data, keep seeded system categories
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def truncate_tables(
    integration_settings: dict,
    run_migrations: None,
) -> None:
    db_url = integration_settings["database_settings"].database_url
    engine = create_async_engine(db_url, poolclass=NullPool)
    async with engine.begin() as conn:
        # DELETE (not TRUNCATE) preserves system categories (user_id IS NULL).
        # FK ON DELETE CASCADE handles user-owned categories, transactions, sessions, etc.
        await conn.execute(sa.text("DELETE FROM outbox_events"))
        await conn.execute(sa.text("DELETE FROM users"))
    await engine.dispose()


# ---------------------------------------------------------------------------
# HTTP client fixture — fresh per test (no shared cookie jar)
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(integration_settings: dict, run_migrations: None) -> AsyncClient:
    app = make_app(**integration_settings)
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as c,
    ):
        yield c
