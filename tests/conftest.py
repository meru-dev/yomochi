import os
import subprocess
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.main.api.app_factory import make_app
from app.main.config.settings import AppSettings, AuthSettings, ObservabilitySettings
from tests.fixtures.personas.loader import PERSONAS, load_fixture

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def test_app_settings() -> AppSettings:
    return AppSettings(_env_file=None, debug=True)


@pytest.fixture(scope="session")
def test_auth_settings() -> AuthSettings:
    return AuthSettings(
        _env_file=None,
        jwt_secret="test-secret",
        debug=True,
        cookie_secure=False,
    )


@pytest.fixture(scope="session")
def test_observability_settings() -> ObservabilitySettings:
    return ObservabilitySettings(
        _env_file=None,
        otel_enabled=False,
        log_format="console",
    )


@pytest.fixture
async def app(
    test_app_settings: AppSettings,
    test_auth_settings: AuthSettings,
    test_observability_settings: ObservabilitySettings,
) -> object:
    return make_app(
        app_settings=test_app_settings,
        auth_settings=test_auth_settings,
        observability_settings=test_observability_settings,
    )


@pytest.fixture
async def client(app: object) -> AsyncGenerator[AsyncClient]:
    async with (
        LifespanManager(app) as manager,  # type: ignore[arg-type]
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as c,
    ):
        yield c


@pytest.fixture(params=PERSONAS)
def persona_fixture(request: pytest.FixtureRequest) -> dict:
    """Persona fixture dict with dates shifted to today's 90-day window."""
    return load_fixture(request.param)


# ---------------------------------------------------------------------------
# Shared infrastructure — used by integration + smoke tests.
# --external-infra: reads DATABASE_URL / REDIS_URL from env (CI services:).
# default: testcontainers spins up one pair for the whole session.
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--external-infra",
        action="store_true",
        default=False,
        help="Use DATABASE_URL / REDIS_URL from env instead of testcontainers.",
    )


@pytest.fixture(scope="session")
def postgres_url(request: pytest.FixtureRequest) -> Generator[str]:
    if request.config.getoption("--external-infra"):
        yield os.environ["DATABASE_URL"]
        return
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        yield pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
def redis_url(request: pytest.FixtureRequest) -> Generator[str]:
    if request.config.getoption("--external-infra"):
        yield os.environ["REDIS_URL"]
        return
    with RedisContainer("redis:7-alpine") as r:
        host = r.get_container_host_ip()
        port = r.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def run_migrations(postgres_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": postgres_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Alembic migrations failed:\n{result.stdout}\n{result.stderr}"
