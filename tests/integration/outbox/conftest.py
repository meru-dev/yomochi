import os
import subprocess
import sys

import pytest
from testcontainers.postgres import PostgresContainer

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest.fixture(scope="module")
def pg_url() -> str:
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        env = {**os.environ, "DATABASE_URL": url}
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=_ROOT,
            capture_output=True,
            check=True,
            env=env,
        )
        yield url
